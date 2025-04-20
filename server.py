import sqlite3
import socket
import threading
import json
import redis

# Connect to Redis
#TODO Understand
redis_client = redis.Redis(host='localhost', port=6379, db=0)

# Connect to SQLite database
conn = sqlite3.connect("lms.db", check_same_thread=False)
cursor = conn.cursor()

# Create tables if they don't exist
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE,
    password TEXT,
    role TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS courses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id TEXT,
    resource_url TEXT,
    poster_username TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
)
""")

# New table for subscriptions
cursor.execute("""
CREATE TABLE IF NOT EXISTS subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT,
    course_id TEXT,
    last_viewed DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(username, course_id)
)
""")

conn.commit()

# Function to register users
def register_user(role, username, password):
    try:
        cursor.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                     (username, password, role))
        conn.commit()
        return "Registration Successful"
    except sqlite3.IntegrityError:
        return "Error: Username already exists!"

# Function to login users
def login_user(username, password):
    cursor.execute("SELECT role FROM users WHERE username=? AND password=?",
                 (username, password))
    result = cursor.fetchone()
    if result:
        return f"Login successful {result[0]}"  # Returns role (student/instructor)
    return "Error: Invalid credentials"

# Function to upload course resources
def upload_course_resources(course_id, resource_url, poster_username):
    try:
        cursor.execute("INSERT INTO courses (course_id, resource_url, poster_username) VALUES (?, ?, ?)",
                     (course_id, resource_url, poster_username))
        conn.commit()
        
        # Publish notification to Redis channel
        notification = {
            "course_id": course_id,
            "resource_url": resource_url,
            "poster_username": poster_username
        }
        redis_client.publish(f"course:{course_id}", json.dumps(notification))
        
        return "Resource Added Successfully"
    except Exception as e:
        return f"Error: {str(e)}"

# Function to get all course resources
def get_course_resource(course_id):
    try:
        cursor.execute("SELECT resource_url FROM courses WHERE course_id=?", (course_id,))
        result = cursor.fetchall()
        if not result:
            return "Error: No resources found for this course!"
        resource_urls = "|".join([row[0] for row in result])
        return resource_urls
    except Exception as e:
        return f"Error: {str(e)}"

# Function to get new resources since last view
def get_new_resources(username, course_id):
    try:
        cursor.execute("""
            SELECT resource_url FROM courses c
            WHERE c.course_id = ? 
            AND c.timestamp > (
                SELECT last_viewed FROM subscriptions 
                WHERE username = ? AND course_id = ?
            )
        """, (course_id, username, course_id))
        
        result = cursor.fetchall()
        if not result:
            return "No new resources"
        
        # Update last viewed timestamp
        cursor.execute("""
            UPDATE subscriptions 
            SET last_viewed = CURRENT_TIMESTAMP 
            WHERE username = ? AND course_id = ?
        """, (username, course_id))
        conn.commit()
        
        return "|".join([row[0] for row in result])
    except Exception as e:
        return f"Error: {str(e)}"

# Function to get all courses
def get_all_courses():
    try:
        cursor.execute("SELECT DISTINCT course_id FROM courses")
        courses = cursor.fetchall()
        if not courses:
            return "No courses available"
        return "|".join([c[0] for c in courses])
    except Exception as e:
        return f"Error: {str(e)}"

# Function to subscribe to a course
def subscribe_to_course(username, course_id):
    try:
        # Check if course exists
        cursor.execute("SELECT 1 FROM courses WHERE course_id = ?", (course_id,))
        if not cursor.fetchone():
            return "Error: Course does not exist!"
            
        cursor.execute("""
            INSERT OR REPLACE INTO subscriptions (username, course_id, last_viewed) 
            VALUES (?, ?, CURRENT_TIMESTAMP)
        """, (username, course_id))
        conn.commit()
        return f"Successfully subscribed to course {course_id}"
    except Exception as e:
        return f"Error: {str(e)}"

# Function to get subscribed courses
def get_subscribed_courses(username):
    try:
        cursor.execute("""
            SELECT course_id FROM subscriptions
            WHERE username = ?
        """, (username,))
        
        courses = cursor.fetchall()
        if not courses:
            return "No subscribed courses"
        
        return "|".join([course[0] for course in courses])
    except Exception as e:
        return f"Error: {str(e)}"

# Handle client requests
def handle_client(client_socket):
    request = client_socket.recv(1024).decode()
    parts = request.split()
    
    if parts[0] == "REGISTER":
        role, username, password = parts[1], parts[2], parts[3]
        response = register_user(role, username, password)
    elif parts[0] == "LOGIN":
        username, password = parts[1], parts[2]
        response = login_user(username, password)
    elif parts[0] == "GET_COURSES":
        response = get_all_courses()
    elif parts[0] == "GET_RESOURCES":
        course_id = parts[1]
        response = get_course_resource(course_id)
    elif parts[0] == "UPLOAD_RESOURCE":
        course_id, resource_url, poster_username = parts[1], parts[2], parts[3]
        response = upload_course_resources(course_id, resource_url, poster_username)
    elif parts[0] == "SUBSCRIBE":
        username, course_id = parts[1], parts[2]
        response = subscribe_to_course(username, course_id)
    elif parts[0] == "GET_SUBSCRIBED_COURSES":
        username = parts[1]
        response = get_subscribed_courses(username)
    elif parts[0] == "GET_NEW_RESOURCES":
        username, course_id = parts[1], parts[2]
        response = get_new_resources(username, course_id)
    else:
        response = "Invalid request!"
    
    client_socket.send(response.encode())
    client_socket.close()

# Start Server
server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.bind(("0.0.0.0", 5000))
server_socket.listen(5)
print("Server is running on port 5000...")

while True:
    try:
        client_sock, addr = server_socket.accept()
        threading.Thread(target=handle_client, args=(client_sock,)).start()
    except KeyboardInterrupt:
        print("Shutting down server...")
        break