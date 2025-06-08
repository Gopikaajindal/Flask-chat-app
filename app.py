# secure_group_chat/app.py

from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_mail import Mail, Message
from flask_socketio import SocketIO, join_room, leave_room, emit
from db import *
from user import User
from bson import ObjectId
from datetime import datetime
import random

app = Flask(__name__)
app.secret_key = "secret-key"
login_manager = LoginManager(app) #add it to you app
login_manager.login_view = 'login'#if acess protected pages
socketio = SocketIO(app)
mail = Mail(app)

# Email config (setup your SMTP credentials here)
# Looking to send emails in production? Check out our Email API/SMTP product!
app.config['MAIL_SERVER']='sandbox.smtp.mailtrap.io'
app.config['MAIL_PORT'] = 2525
app.config['MAIL_USERNAME'] = '5e9ef1bd194b91'
app.config['MAIL_PASSWORD'] = 'e7a03174a66561'
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False
mail = Mail(app)
otp_store = {}

@login_manager.user_loader
def load_user(username):
    return get_user(username)

@app.route('/')
@login_required
def index():
    rooms = get_rooms_for_user(current_user.username)
    return render_template('index.html', rooms=rooms)

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        otp = str(random.randint(100000, 999999))
        otp_store[email] = {'otp': otp, 'username': username, 'password': password}

        msg = Message('OTP Verification', sender='noreply@securechat.com', recipients=[email])
        msg.body = f"Your OTP is: {otp}"
        mail.send(msg)
        flash('OTP sent to your email.')
        return redirect(url_for('verify_otp', email=email))
    return render_template('signup.html')

@app.route('/verify-otp/<email>', methods=['GET', 'POST'])
def verify_otp(email):
    if request.method == 'POST':
        input_otp = request.form['otp']
        record = otp_store.get(email)
        if record and record['otp'] == input_otp:
            save_user(record['username'], email, record['password'])
            del otp_store[email]
            flash('Signup successful, please log in.')
            return redirect(url_for('login'))
        flash('Invalid OTP.')
    return render_template('verify_otp.html', email=email)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = get_user(username)
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('index'))
        flash('Invalid credentials')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/create-room/', methods=['GET', 'POST'])
@login_required
def create_room():
    if request.method == 'POST':
        room_name = request.form['room_name']
        party2 = request.form['party2']
        party3 = request.form['party3']
        room_id = save_room(room_name, current_user.username)
        add_room_member(room_id, room_name, current_user.username, current_user.username, is_room_admin=True)
        add_room_member(room_id, room_name, party2, current_user.username)
        add_room_member(room_id, room_name, party3, current_user.username)
        return redirect(url_for('index'))
    return render_template('create_room.html')

@app.route('/rooms/<room_id>/moderate')
@login_required
def moderate_room(room_id):
    if not is_room_admin(room_id, current_user.username):
        return "Unauthorized", 403
    messages = get_pending_messages(room_id)
    return render_template('moderate.html', messages=messages, room_id=room_id)

@app.route('/rooms/<room_id>/chat')
@login_required
def chat_room(room_id):
    room = get_room(room_id)
    if not room:
        return "Room not found", 404
    if not is_room_admin(room_id, current_user.username) and not is_room_member(room_id, current_user.username):
        return "Unauthorized", 403

    approved_messages = get_approved_messages(room_id, current_user.username)
    room_members = get_room_members(room_id)
    return render_template(
        'chat_room.html',
        room=room,
        username=current_user.username,
        messages=approved_messages,
        room_members=room_members
    )

@app.route('/moderate-action/', methods=['POST'])
@login_required
def moderate_action():
    msg_id = request.form['msg_id']
    action = request.form['action']
    msg = messages_collection.find_one({'_id': ObjectId(msg_id)})
    if not msg:
        return redirect(request.referrer)

    if action == 'accept':
        approve_message(msg_id)
    elif action == 'modify':
        new_text = request.form['new_message']
        modify_and_approve_message(msg_id, new_text)
        msg['content'] = new_text
    elif action == 'block':
        delete_message(msg_id)
        return redirect(request.referrer)

    socketio.emit('new_message', {
        'room_id': str(msg['room_id']),
        'sender': msg['sender'],
        'recipient': msg['recipient'],
        'content': msg['content'],
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M')
    },)

    return redirect(request.referrer)

@app.context_processor
def utility_processor():
    return dict(is_room_admin=is_room_admin)

@socketio.on('send_message')
def handle_send(data):
    sender = data['username']
    recipient = data['to']
    room = data['room']
    message = data['message']
    save_message_for_approval(room, sender, recipient, message)
    emit('pending', {'status': 'Message sent for moderation.'}, to=request.sid)

@app.route('/rooms/<room_id>/delete', methods=['POST'])
@login_required
def delete_room(room_id):
    if not is_room_admin(room_id, current_user.username):
        return "Unauthorized", 403
    rooms_collection.delete_one({'_id': ObjectId(room_id)})
    room_members_collection.delete_many({'_id.room_id': ObjectId(room_id)})
    messages_collection.delete_many({'room_id': ObjectId(room_id)})
    flash('Room and all messages deleted.')
    return redirect(url_for('index'))

@app.route('/rooms/<room_id>/delete-chat', methods=['POST'])
@login_required
def delete_chat(room_id):
    if not is_room_admin(room_id, current_user.username):
        return "Unauthorized", 403
    messages_collection.delete_many({'room_id': ObjectId(room_id)})
    flash('Chat messages deleted.')
    return redirect(url_for('index'))

if __name__ == '__main__':
    socketio.run(app, debug=True)
