import socket

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 5000

def send_request(message):
    try:
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_socket.connect((SERVER_HOST, SERVER_PORT))
        client_socket.send(message.encode())
        response = client_socket.recv(1024).decode()
        client_socket.close()
        return response
    except Exception as e:
        return f"Error: {str(e)}"