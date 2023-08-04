import os
import uuid
import openai
import random
import json
import jwt
import datetime
from flask import Flask, send_from_directory, request, jsonify, make_response, session
from flask_security import SQLAlchemyUserDatastore, Security, login_user
from flask_login import LoginManager, login_required, current_user, logout_user
from flask_cors import CORS, cross_origin
from flask_wtf.csrf import generate_csrf
from models import GeneratedText, User, FitnessProfile
from app import app, user_datastore, load_user
from extensions import db
from flask_security.utils import hash_password, verify_password

def create_auth_token_for(user):
    payload = {
        'user_id': user.id,  
        'exp': datetime.datetime.utcnow() + datetime.timedelta(days=1)  
    }
    token = jwt.encode(payload, app.config['SECRET_KEY'], algorithm='HS256')
    return token.decode()

@app.route("/")
def base():
    return send_from_directory('client/static', 'index.html')

@app.route("/<path:path>")
def home(path):
    return send_from_directory('client/static', path)

@app.route('/generate', methods=['POST'])
@login_required
def generate():
    try:
        prompt = request.json['prompt']
        max_tokens = request.json.get('max_tokens', 1000)

        response = openai.ChatCompletion.create(
          model="gpt-3.5-turbo",  # replace with appropriate GPT-4 model when available
          messages=[{"role": "user", "content": prompt}],
        )

        response_text = response.choices[0].message.content.strip()

        # create a new GeneratedText object with the prompt and response, and add it to the db
        new_generated_text = GeneratedText(prompt, response_text, current_user.id)
        db.session.add(new_generated_text)
        db.session.commit()

        return jsonify(response_text)
    except Exception as e:
        return jsonify(error=str(e)), 500

@app.route('/responses', methods=['GET'])
@login_required
def get_responses():
    try:
        # query the database for all responses
        responses = GeneratedText.query.filter_by(user_id=current_user.id)

        # convert the list of SQLAlchemy Objects to a list of dictionaries
        responses_list = [{"id": response.id, "prompt": response.prompt, "response": response.response} for response in responses]
        return jsonify(responses_list)
    except Exception as e:
        return jsonify(error=str(e)), 500

@app.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    return jsonify({'message': 'Logged out'}), 200

@app.route('/login', methods=['POST'])
@cross_origin(supports_credentials=True) # This will enable CORS for the login route
def login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    
    if not email or not password:
        return jsonify(success=False, message='Missing email or password'), 400

    user = User.query.filter_by(email=email).first()
    
    if user and user.check_password(password):
        login_user(user)
        session['logged_in'] = True  
        auth_token = create_auth_token_for(user)  # Replace with your function to create an auth token
        resp = make_response(jsonify(success=True, message='Logged in successfully', auth_token=auth_token), 200)
    else:
        resp = make_response(jsonify(success=False, message='Invalid credentials'), 401)
    
    resp.set_cookie('csrf_access_token', generate_csrf())  # Set the CSRF token here
    return resp

@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()

    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        return jsonify(success=False, error='Email and password required'), 400

    user = User.query.filter_by(email=email).first()

    # If this returns a user, then the email already exists in database
    if user:
        return jsonify(success=False, error='A user with that email already exists.'), 400

    user = user_datastore.create_user(email=email, password=hash_password(password), active=True)

    if not user:
        return jsonify(success=False, error='There was an error creating your account. Please try again.'), 400

    db.session.commit()

    return jsonify(success=True, message='Successfully registered. You can now log in.')
