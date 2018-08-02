from models import Server_old, User, Sound, session, Server

for server in session.query(Server_old).all():
    for name, data in server.sounds.items():
        s = Sound(name=name, url=data['url'], server_id=server.id)
        session.add(s)

    new_server = Server(id=server.id, prefix='?', roles=['off'])
    session.add(new_server)

    session.commit()
