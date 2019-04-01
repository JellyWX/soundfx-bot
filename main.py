from models import Server, session, User, Sound

from ctypes.util import find_library
import discord ## pip3 install git+...
import sys
import os
import aiohttp ## pip3 install aiohttp
from aiohttp import web
import asyncio
import json # send requests
import time # check delays
from configparser import SafeConfigParser # read config
import traceback # error grabbing
import io
import sqlalchemy
import subprocess
import concurrent.futures
from functools import partial

from sqlalchemy.sql.expression import func


check_digits = lambda x: all( [y in '0123456789' for y in x] ) and len(x)

class BotClient(discord.AutoShardedClient):
    def __init__(self, *args, **kwargs):
        super(BotClient, self).__init__(*args, **kwargs)

        self.color = 0xff3838

        self.MAX_SOUNDS = 8

        self.file_indexing = 0

        self.commands = {
            'ping' : self.ping,
            'help' : self.help,
            'info' : self.info,
            'invite' : self.info,

            'prefix' : self.change_prefix,
            'upload' : self.wait_for_file,

            'play' : self.play,
            'stop' : self.stop,

            'list' : self.list,
            'delete' : self.delete,
            'roles' : self.role,

            'greet' : self.greet,
            'public' : self.public,

            'search' : self.search,
            'new' : self.search,
            'popular' : self.search,
            'random' : self.search,
        }


        self.config = SafeConfigParser()
        self.config.read('config.ini')

        self.executor = concurrent.futures.ThreadPoolExecutor()


    async def do_blocking(self, method):
        a, _ = await asyncio.wait([self.loop.run_in_executor(self.executor, method)])
        return [x.result() for x in a][0]


    async def send(self):
        guild_count = len(self.guilds)

        if self.config.get('TOKENS', 'discordbots'):

            session = aiohttp.ClientSession()
            dump = json.dumps({
                'server_count': len(client.guilds)
            })

            head = {
                'authorization': self.config.get('TOKENS', 'discordbots'),
                'content-type' : 'application/json'
            }

            url = 'https://discordbots.org/api/bots/stats'
            async with session.post(url, data=dump, headers=head) as resp:
                print('returned {0.status} for {1}'.format(resp, dump))

            await session.close()


    async def on_ready(self):
        discord.opus.load_opus(find_library('opus'))

        print('Logged in as')
        print(self.user.name)
        print(self.user.id)
        print('------------')
        await client.change_presence(activity=discord.Game(name='@{} info'.format(self.user.name)))


    async def on_guild_join(self, guild):
        await self.send()

        await self.welcome(guild)


    async def on_guild_remove(self, guild):
        await self.send()


    async def welcome(self, guild, *args):
        if isinstance(guild, discord.Message):
            guild = guild.guild

        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages and not channel.is_nsfw():
                await channel.send('Thank you for adding SoundFX! To begin, type `?info` to learn more.')
                break
            else:
                continue


    async def check_and_play(self, guild, channel, caller, sound, server):
        if 'off' not in server.roles and not caller.guild_permissions.manage_guild:
            for role in caller.roles:
                if role.id in server.roles:
                    break
            else:
                await channel.send('You aren\'t allowed to do this. Please tell a moderator to do `{}roles` to set up permissions'.format(server.prefix))
                return

        if caller.voice is None:
            await channel.send('You aren\'t in a voice channel.')

        elif not caller.voice.channel.permissions_for(guild.me).connect:
            await channel.send('No permissions to connect to channel.')

        else:
            await self.play_sound(caller.voice.channel, sound)


    async def play_sound(self, v_c, sound):
        if sound.src is None:
            sound.src = await self.store(sound.url)

        perms = v_c.permissions_for(v_c.guild.me)

        if perms.connect() and perms.speak():
            src = sound.src

            try:
                voice = await v_c.connect()
            except discord.errors.ClientException:
                voice = [v for v in self.voice_clients if v.channel.guild == v_c.guild][0]
                if voice.channel != v_c:
                    await voice.disconnect(force=True)
                    voice = await v_c.connect()

            if voice.is_playing():
                voice.stop()

            self.file_indexing += 1
            self.file_indexing %= 1000

            filename = '/tmp/file-{}'.format(self.file_indexing)

            with open(filename, 'wb') as f:
                f.write(src)

            voice.play(discord.FFmpegPCMAudio(filename))

            if sound.plays is None:
                sound.plays = 1
            else:
                sound.plays += 1

            session.commit()


    async def check_premium(self, user):
        premium = False

        async with aiohttp.ClientSession() as cs:
            async with cs.get('https://fusiondiscordbots.com/api/user/subscriptions/{}'.format(user)) as request:
                t = await request.read()
                if 'soundfx' in str(t):
                    premium = True

        return premium


    async def store(self, url):
        m = await self.do_blocking( partial(self.b_store, url) )
        return m


    def b_store(self, url):
        sub = subprocess.Popen(('ffmpeg', '-i', url, '-loglevel', 'error', '-b:a', '28000', '-f', 'opus', 'pipe:1'), stdout=subprocess.PIPE)

        out = sub.stdout.read()
        if len(out) < 1:
            return b''

        else:
            return out


    def delete_sound(self, s):
        u = session.query(User).filter(User.join_sound_id == s.first().id)

        s.delete(synchronize_session='fetch')


    async def on_web_ping(self, request):
        params = request.rel_url.query

        if all(x in params.keys() for x in ('id', 'user')):
            m = [y for y in self.get_all_members() if y.id == int(params['user']) and y.voice is not None]

            if len(m) == 0:
                return web.Response(text='Not in voice channel', status=400)

            else:
                m = m[0]

            s = session.query(Sound).get(params['id'])

            await self.play_sound(m.voice.channel, s)

            return web.Response(text='OK')

        else:
            return web.Response(text='Missing parameters', status=400)


    async def on_voice_state_update(self, member, before, after):
        user = session.query(User).filter(User.id == member.id).first()
        if user is None:
            return

        server = session.query(Server).filter_by(id=member.guild.id).first()

        if before.channel != after.channel and after.channel is not None \
            and user.join_sound is not None:

            if user.join_sound.public:

                await self.play_sound(member.voice.channel, user.join_sound)
                print('Playing join sound')

            else:
                user.join_sound = None


    async def on_error(self, e, *a, **k):
        session.rollback()
        raise


    async def on_message(self, message):

        if isinstance(message.channel, discord.DMChannel) or message.author.bot or message.content is None:
            return

        if session.query(Server).filter_by(id=message.guild.id).first() is None:
            s = Server(id=message.guild.id, prefix='?', roles=['off'])
            session.add(s)
            session.commit()

        if session.query(User).filter_by(id=message.author.id).first() is None:
            s = User(id=message.author.id)
            session.add(s)
            session.commit()

        try:
            if await self.get_cmd(message):
                session.commit()

        except Exception as e:
            traceback.print_exc()
            await message.channel.send('Internal exception detected in command, {}'.format(e))


    async def get_cmd(self, message):

        server = session.query(Server).filter_by(id=message.guild.id).first()
        prefix = server.prefix

        command = None

        if message.content[0:len(prefix)] == prefix:
            command = (message.content + ' ')[len(prefix):message.content.find(' ')]
            stripped = (message.content + ' ')[message.content.find(' '):].strip()

        elif self.user.id in map(lambda x: x.id, message.mentions) and len(message.content.split(' ')) > 1:
            command = message.content.split(' ')[1]
            stripped = (message.content + ' ').split(' ', 2)[-1].strip()

        if command is not None:
            if command in self.commands.keys():
                await self.commands[command](message, stripped, server)
                return True

            else:
                s = server.sounds.filter(Sound.name == '{} {}'.format(command, stripped).strip()).first()

                if s is not None:
                    await self.play(message, '{} {}'.format(command, stripped).strip(), server)

        return False


    async def change_prefix(self, message, stripped, server):

        if message.author.guild_permissions.manage_guild:

            if stripped:
                stripped += ' '
                new = stripped[:stripped.find(' ')]

                if len(new) > 5:
                    await message.channel.send('Prefix must be shorter than 5 characters')

                else:
                    server.prefix = new
                    await message.channel.send('Prefix changed to {}'.format(server.prefix))

            else:
                await message.channel.send('Please use this command as `{}prefix <prefix>`'.format(server.prefix))

        else:
            await message.channel.send('Please ensure you have the `manage guild` permission to run this command.')


    async def ping(self, message, stripped, server):
        t = message.created_at.timestamp()
        e = await message.channel.send('pong')
        delta = e.created_at.timestamp() - t

        await e.edit(content='Pong! {}ms round trip'.format(round(delta * 1000)))


    async def help(self, message, stripped, server):
        embed = discord.Embed(title='HELP', color=self.color, description='Please visit https://soundfx.jellywx.com/help/'.format(self.user.name))
        await message.channel.send(embed=embed)


    async def info(self, message, stripped, server):
        em = discord.Embed(title='INFO', color=self.color, description=
        '''\u200B
Default prefix: `?`

Reset prefix: `@{user} prefix ?`
Help: `{p}help`

Invite me: https://discordapp.com/oauth2/authorize?client_id=430384808200372245&scope=bot&permissions=36703232

**Welcome to SFX!**
Developer: <@203532103185465344>
Find me on https://discord.gg/q2pRJQZ and on https://github.com/JellyWX :)

An online dashboard is available! Visit https://soundfx.jellywx.com/dashboard
There is a maximum sound limit per user. This can be removed by donating at https://fusiondiscordbots.com/premium

*If you have enquiries about new features, please send to the discord server*
*If you have enquiries about bot development for you or your server, please DM me*
        '''.format(user=self.user.name, p=server.prefix)
        )

        await message.channel.send(embed=em)

        await message.add_reaction('📬')


    async def role(self, message, stripped, server):
        if message.author.guild_permissions.manage_guild:

            if stripped == '@everyone':
                server.roles = ['off']

                await message.channel.send('Role blacklisting disabled.')

            elif len(message.role_mentions) > 0:
                roles = [x.id for x in message.role_mentions]

                server.roles = roles

                await message.channel.send('Roles set. Please note members with `Manage Server` permissions will be able to do sounds regardless of roles.')

            else:
                if server.roles[0] == 'off':
                    await message.channel.send('Please mention roles or `@everyone` to blacklist roles.')
                else:
                    await message.channel.send('Please mention roles or `@everyone` to blacklist roles. Current roles are <@&{}>'.format('>, <@&'.join([str(x) for x in server.roles])))

        else:
            await message.channel.send('You must have permission `Manage Server` to perform this command.')


    async def wait_for_file(self, message, stripped, server):
        stripped = stripped.lower()

        if 'off' not in server.roles and not message.author.guild_permissions.manage_guild:
            for role in message.author.roles:
                if role.id in server.roles:
                    break
            else:
                await message.channel.send('You aren\'t allowed to do this. Please tell a moderator to do `{}roles` to set up permissions'.format(server.prefix))
                return

        premium = await self.check_premium(message.author.id)

        user = session.query(User).filter(User.id == message.author.id).first()

        if len(user.sounds) >= self.MAX_SOUNDS and not premium:
            await message.channel.send('Sorry, but the maximum is {} sounds per user. You can either use `{prefix}delete` to remove a sound or donate to get unlimited sounds at https://fusiondiscordbots.com/premium'.format(self.MAX_SOUNDS, prefix=server.prefix))

        elif stripped == '':
            await message.channel.send('Please provide a name for your sound in the command, e.g `?upload TERMINATION`')

        elif check_digits(stripped):
            await message.channel.send('Please use at least one non-numerical character in your sound\'s name (this helps distunguish it from IDs)')

        elif len(stripped) > 20:
            await message.channel.send('Please keep your names concise. You used {}/20 characters.'.format(len(stripped)))

        else:
            sound = session.query(Sound).filter(Sound.server_id == message.guild.id).filter(Sound.name == stripped)
            s = sound.first()

            await message.channel.send('Saving as: `{}`. Send an audio file <500KB (1MB for premium users) or send any other message to cancel.'.format(stripped))

            msg = await self.wait_for('message', check=lambda x: x.author == message.author and x.channel == message.channel)

            if msg.attachments == []:
                await message.channel.send('Please attach an MP3/OGG file following the `{}upload` command. Aborted.'.format(server.prefix))

            else:
                out = await self.store(msg.attachments[0].url)

                if len(out) < 1:
                    await message.channel.send('File not recognized as being a valid audio file.')

                elif (len(out) > 350000 and not premium) or (len(out) > 1000000 and premium):
                    await message.channel.send('Please only send audio files that are under 350kB serverside compressed (1MB if premium user). The bot uses Opus 28kbps compression when storing audio.')

                else:
                    if s is not None:
                        self.delete_sound(sound)

                    sound = Sound(url=msg.attachments[0].url, src=out, server=server, user=user, name=stripped, plays=0, big=len(out) > 350000)

                    session.add(sound)

                    response = await message.channel.send('Sound saved as `{name}`! Use `{prefix}play {name}` to play the sound. **Please do not delete the file from Discord.**'.format(name=stripped, prefix=server.prefix))


    async def play(self, message, stripped, server):
        stripped = stripped.lower()

        if stripped == '':
            await message.channel.send('You must specify the sound you wish to play. Use `{}list` to view all sounds.'.format(server.prefix))

        elif stripped.startswith('id:') and check_digits(stripped[3:]):
            id = int( stripped[3:] )
            s = session.query(Sound).filter(Sound.public).filter(Sound.id == id).first()

            if s is None:
                await message.channel.send('No sound found by ID')
                return

        else:
            s = session.query(Sound).filter_by(server_id=message.guild.id, name=stripped).first()

            if s is None:
                s = session.query(Sound).filter_by(uploader_id=message.author.id, name=stripped).first()

        if s is None: ## if none in current server by name:
            sq = session.query(Sound).filter( Sound.public ).filter( Sound.name == stripped ).order_by( func.rand() ) ## query by name
            s = sq.first()

            if sq.count() > 1:

                g = self.get_guild(s.server_id)

                if g is not None:
                    name = g.name
                else:
                    name = None

                await message.channel.send('Mutiple sounds with name specified. Consider using `{}play ID:1234` to specify an ID. Playing {} (ID {}) from {}...'.format( server.prefix, s.name, s.id, name ))

                await self.check_and_play(message.guild, message.channel, message.author, s, server)

            elif sq.count() == 0:

                await message.channel.send('Sound `{0}` could not be found in server or in Sound Repository by name. Use `{1}list` to view all sounds, `{1}search` to search for public sounds, or `{1}play ID:1234` to play a sound by ID'.format(stripped, server.prefix))

            else:
                g = self.get_guild(s.server_id)

                if g is not None:
                    name = g.name
                else:
                    name = None

                await message.channel.send('Playing public sound {name} (ID {id}) from {guild}'.format(
                    name = s.name,
                    id = s.id,
                    guild = name,
                    pref = server.prefix
                    )
                )

                await self.check_and_play(message.guild, message.channel, message.author, s, server)

        else:
            await self.check_and_play(message.guild, message.channel, message.author, s, server)


    async def stop(self, message, stripped, server):

        voice = [v for v in self.voice_clients if v.channel.guild == message.guild]
        if len(voice) == 0:
            await message.channel.send('Not connected to a VC!')
        else:
            await voice[0].disconnect(force=True)


    async def list(self, message, stripped, server):

        strings = []

        if 'me' in stripped:
            user = session.query(User).filter(User.id == message.author.id).first()
            a = user.sounds
        else:
            a = server.sounds

        for s in a:
            string = '**{}**'.format(s.name, s)
            if s.public:
                string += ' (\U0001F513)'
            else:
                string += ' (\U0001F510)'

            strings.append(string)

        if 'me' in stripped:
            await message.channel.send('All your sounds: {}'.format(', '.join(strings)))
        else:
            await message.channel.send('All sounds on this server: {}'.format(', '.join(strings)))


    async def delete(self, message, stripped, server):
        stripped = stripped.lower()

        user = session.query(User).filter(User.id == message.author.id).first()

        u = session.query(Sound).filter(Sound.uploader_id == message.author.id).filter(Sound.name == stripped)

        if u.first() is None:
            if 'off' not in server.roles and not message.author.guild_permissions.manage_guild:
                for role in message.author.roles:
                    if role.id in server.roles:
                        break
                else:
                    await message.channel.send('You aren\'t allowed to do this. Please tell a moderator to do `{}roles` to set up permissions'.format(server.prefix))
                    return

            s = server.sounds.filter(Sound.name == stripped)

            if s.first() is not None:
                self.delete_sound(s)
                await message.channel.send('Deleted `{}`. You have used {}/{} sounds.'.format(stripped, len(user.sounds), self.MAX_SOUNDS))
            else:
                await message.channel.send('Couldn\'t find sound by name {}. Use `{}list` to view all sounds.'.format(stripped, server.prefix))

        else:
            self.delete_sound(u)
            await message.channel.send('Deleted `{}`. You have used {}/{} sounds.'.format(stripped, len(user.sounds), self.MAX_SOUNDS))


    async def public(self, message, stripped, server):
        stripped = stripped.lower()

        s = server.sounds.filter(Sound.name == stripped).first()

        if 'off' not in server.roles and not message.author.guild_permissions.manage_guild:
            for role in message.author.roles:
                if role.id in server.roles:
                    break
            else:
                await message.channel.send('You aren\'t allowed to do this. Please tell a moderator to do `{}roles` to set up permissions'.format(server.prefix))
                return

        count = server.sounds.filter(Sound.public).count()

        if s is not None:

            s.public = not s.public
            await message.channel.send('Sound `{}` has been set to {}.'.format(stripped, 'public \U0001F513' if s.public else 'private \U0001F510'))
        else:
            await message.channel.send('Couldn\'t find sound by name {}. Use `{}list` to view all sounds.'.format(stripped, server.prefix))


    async def search(self, message, stripped, server):

        embed = discord.Embed(title='Public sounds matching filter:')

        length = 0

        if 'new' in message.content.split(' ')[0]:
            for sound in session.query(Sound).filter(Sound.public).order_by(Sound.id.desc()):
                if length < 1900:
                    g = self.get_guild(sound.server_id)

                    if g is not None:
                        name = g.name
                    else:
                        name = None

                    content = 'ID: {}\nGuild: {}'.format(sound.id, name)

                    embed.add_field(name=sound.name, value=content, inline=True)

                    length += len(content) + len(sound.name)

        elif 'popular' in message.content.split(' ')[0]:
            for sound in session.query(Sound).filter(Sound.public).order_by(Sound.plays.desc()):
                if length < 1900:
                    content = 'ID: {}\nPlays: {}'.format(sound.id, sound.plays)

                    embed.add_field(name=sound.name, value=content, inline=True)

                    length += len(content) + len(sound.name)

        elif 'random' in message.content.split(' ')[0]:
            for sound in session.query(Sound).filter(Sound.public).order_by(func.rand()):
                if length < 1900:
                    g = self.get_guild(sound.server_id)

                    if g is not None:
                        name = g.name
                    else:
                        name = None

                    content = 'ID: {}\nGuild: {}'.format(sound.id, name)

                    embed.add_field(name=sound.name, value=content, inline=True)

                    length += len(content) + len(sound.name)

        else:
            for sound in session.query(Sound).filter(Sound.public).filter(Sound.name.ilike('%{}%'.format(stripped))):
                if length < 1900:
                    g = self.get_guild(sound.server_id)

                    if g is not None:
                        name = g.name
                    else:
                        name = None

                    content = 'ID: {}\nGuild: {}'.format(sound.id, name)

                    embed.add_field(name=sound.name, value=content, inline=True)

                    length += len(content) + len(sound.name)

                else:
                    embed.set_footer(text='More results were found, but removed due to size restrictions')
                    break

        await message.channel.send(embed=embed)


    async def greet(self, message, stripped, server):
        user = session.query(User).filter(User.id == message.author.id).first()
        stripped = stripped.lower()


        if stripped == '' and user.join_sound is not None:
            user.join_sound = None
            await message.channel.send('You have unassigned your greet sound')

        elif check_digits(stripped):
            id = int( stripped )

            sound = session.query(Sound).filter(Sound.public).filter(Sound.id == id).first()

            if user is None:
                user = User(id=message.author.id, join_sound=None)
                session.add(user)
                session.commit()

            if sound is not None:
                user.join_sound = sound
                await message.channel.send('Your greet sound has been set.')

            else:
                await message.channel.send('No public sound found with ID {}'.format(id))

        else:
            await message.channel.send('Please specify a numerical ID. You can find IDs using the search command.')


    async def cleanup(self):
        await self.wait_until_ready()
        while not client.is_closed():

            [await vc.disconnect(force=True) for vc in self.voice_clients if not vc.is_playing()]
            await asyncio.sleep(180)


client = BotClient()

app = web.Application()
app.add_routes([web.get('/play', client.on_web_ping)])

handler = app.make_handler()

try:
    client.loop.create_task(client.cleanup())

    coro = client.loop.create_server(handler, host='127.0.0.1', port=7765)
    client.loop.create_task(coro)

    client.run(client.config.get('TOKENS', 'bot'), max_messages=50)
except Exception as e:
    print('Error detected. Restarting in 15 seconds.')
    print(sys.exc_info())
    time.sleep(15)

    os.execl(sys.executable, sys.executable, *sys.argv)

