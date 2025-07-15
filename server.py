
# Nuevo servidor Socket.IO compatible con el cliente
import socketio
import eventlet
import numpy as np

sio = socketio.Server(logger=False, engineio_logger=False)
app = socketio.WSGIApp(sio)

users = {}
user_to_room = {}

@sio.event
def connect(sid, environ):
	print(f"Client connected: {sid}")
	

@sio.event
def disconnect(sid):
	code = user_to_room[sid]
	sio.emit('disconnect_user', room=code)
	sio.leave_room(sid, code)

	del user_to_room[sid]

@sio.event
def voice(sid, data):
	# print(f"Received 'voice' event from {sid}. Data type: {type(data)}")
	code = user_to_room[sid]
	
	sio.emit('voice', data, room=code)

@sio.event
def chat_message(sid, msg):
	code = user_to_room[sid]

	sio.emit('chat_message', msg, room=code)

@sio.event
def new_user(sid, user):
	code = user["room_code"]
	name = user["name"]
	sio.enter_room(sid, code)

	if users.get(code, None) is None:
		users[code] = {}
	
	users[code][sid] = name
	user_to_room[sid] = code

	for name in users[code].values():
		sio.emit('new_user', name, room=code)

if __name__ == "__main__":
    print("Socket.IO server listening on http://localhost:3500 (sin logs de acceso)...")
    
    # Crear un logger silencioso
    class QuietLogger:
        def write(self, message):
            pass
    
    # Configurar el servidor con logging silencioso
    server = eventlet.listen(('localhost', 3500))
    eventlet.wsgi.server(
        server,
        app,
        log=QuietLogger(),  # Logger personalizado que no muestra nada
        log_output=False     # Desactivar completamente los logs
    )