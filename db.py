# secure_group_chat/db.py

from datetime import datetime
from bson import ObjectId
from pymongo import MongoClient
from werkzeug.security import generate_password_hash
from user import User

client = MongoClient("mongodb+srv://test:test@chatapp.crzcjww.mongodb.net/?retryWrites=true&w=majority&appName=ChatApp")
chat_db = client.get_database("SecureChat")

users_collection = chat_db.get_collection("users")
rooms_collection = chat_db.get_collection("rooms")
room_members_collection = chat_db.get_collection("room_members")
messages_collection = chat_db.get_collection("messages")

# --- User management ---
def save_user(username, email, password):
    password_hash = generate_password_hash(password)
    users_collection.insert_one({'_id': username, 'email': email, 'password': password_hash})

def get_user(username):
    user_data = users_collection.find_one({'_id': username})
    return User(user_data['_id'], user_data['email'], user_data['password']) if user_data else None

# --- Room management ---
def save_room(room_name, created_by):
    room_id = rooms_collection.insert_one({
        'name': room_name,
        'created_by': created_by,
        'created_at': datetime.now()
    }).inserted_id
    return room_id

def get_room(room_id):
    return rooms_collection.find_one({'_id': ObjectId(room_id)})

def get_room_members(room_id):
    return list(room_members_collection.find({'_id.room_id': ObjectId(room_id)}))

def add_room_member(room_id, room_name, username, added_by, is_room_admin=False):
    room_members_collection.insert_one({
        '_id': {'room_id': ObjectId(room_id), 'username': username},
        'room_name': room_name,
        'added_by': added_by,
        'added_at': datetime.now(),
        'is_room_admin': is_room_admin
    })

def get_rooms_for_user(username):
    return list(room_members_collection.find({'_id.username': username}))

def is_room_admin(room_id, username):
    return room_members_collection.count_documents({
        '_id.room_id': ObjectId(room_id),
        '_id.username': username,
        'is_room_admin': True
    }) > 0

def is_room_member(room_id, username):
    return room_members_collection.count_documents({
        '_id.room_id': ObjectId(room_id),
        '_id.username': username
    }) > 0

# --- Messaging moderation ---
def save_message_for_approval(room_id, sender, recipient, content):
    messages_collection.insert_one({
        'room_id': ObjectId(room_id),
        'sender': sender,
        'recipient': recipient,
        'content': content,
        'status': 'pending',
        'created_at': datetime.now()
    })

def get_pending_messages(room_id):
    return list(messages_collection.find({
        'room_id': ObjectId(room_id),
        'status': 'pending'
    }))

def approve_message(msg_id):
    messages_collection.update_one({'_id': ObjectId(msg_id)}, {'$set': {'status': 'approved'}})

def modify_and_approve_message(msg_id, new_content):
    messages_collection.update_one(
        {'_id': ObjectId(msg_id)},
        {'$set': {'content': new_content, 'status': 'approved'}}
    )

def delete_message(msg_id):
    messages_collection.delete_one({'_id': ObjectId(msg_id)})

def get_approved_messages(room_id, username):
    return list(messages_collection.find({
        'room_id': ObjectId(room_id),
        'status': 'approved',
        '$or': [
            {'sender': username},
            {'recipient': username}
        ]
    }).sort('created_at'))
