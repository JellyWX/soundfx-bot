from sloccount import sloccount_py
from server_data import ServerData

from ctypes.util import find_library
import discord ## pip3 install git+...
import sys
import os
import msgpack ## pip3 install msgpack
import zlib
import aiohttp ## pip3 install aiohttp
import io
import magic ## pip3 install python-magic

class BotClient(discord.Client):
    def __init__(self, *args, **kwargs):
        super(BotClient, self).__init__(*args, **kwargs)
        self.get_server = lambda x: [d for d in self.data if d.id == x.id][0]

        self.data = []

        self.commands = {
            'ping' : self.ping,
            'help' : self.help,
            'info': self.info,
            'prefix' : self.change_prefix,
            'upload' : self.wait_for_file,
            'play' : self.play,
            'list' : self.list,
            'delete' : self.delete,
            'debug' : self.debug_play
        }

        try:
            with open('data.mp', 'rb') as f:
                for d in msgpack.unpackb(zlib.decompress(f.read()), encoding='utf8'):
                    self.data.append(ServerData(**d))
        except FileNotFoundError:
            pass


    async def on_ready(self):
        discord.opus.load_opus(find_library('opus'))

        print('Logged in as')
        print(self.user.name)
        print(self.user.id)
        print('------------')
        await client.change_presence(activity=discord.Game(name='@{} info'.format(self.user.name)))


    async def on_guild_join(self, guild):
        self.data.append(ServerData(**{
            'id' : guild.id,
            'prefix' : '?',
            'sounds' : {}
            }
        ))


    async def on_guild_remove(self, guild):
        self.data = [d for d in self.data if d.id != guild.id]


    async def on_message(self, message):

        if isinstance(message.channel, discord.DMChannel) or message.author.bot or message.content == None:
            return

        if len([d for d in self.data if d.id == message.guild.id]) == 0:
            self.data.append(ServerData(**{
                'id' : message.guild.id,
                'prefix' : '?',
                'sounds' : {}
                }
            ))

        if await self.get_cmd(message):
            with open('data.mp', 'wb') as f:
                f.write(zlib.compress(msgpack.packb([d.__dict__ for d in self.data])))


    async def get_cmd(self, message):

        server = self.get_server(message.guild)
        prefix = server.prefix

        if message.content[0:len(prefix)] == prefix:
            command = (message.content + ' ')[len(prefix):message.content.find(' ')]
            if command in self.commands:
                stripped = (message.content + ' ')[message.content.find(' '):].strip()
                await self.commands[command](message, stripped)
                return True

        elif self.user.id in map(lambda x: x.id, message.mentions) and len(message.content.split(' ')) > 1:
            if message.content.split(' ')[1] in self.commands.keys():
                stripped = (message.content + ' ').split(' ', 2)[-1].strip()
                await self.commands[message.content.split(' ')[1]](message, stripped)
                return True

        return False


    async def change_prefix(self, message, stripped):
        server = self.get_server(message.guild)

        if stripped:
            stripped += ' '
            server.prefix = stripped[:stripped.find(' ')]
            await message.channel.send('Prefix changed to {}'.format(server.prefix))

        else:
            await message.channel.send('Please use this command as `{}prefix <prefix>`'.format(server.prefix))


    async def ping(self, message, stripped):
        t = message.created_at.timestamp()
        e = await message.channel.send('pong')
        delta = e.created_at.timestamp() - t

        await e.edit(content='Pong! {}ms round trip'.format(round(delta * 1000)))


    async def help(self, message, stripped):
        embed = discord.Embed(title='HELP', description=
        '''
`?help` : view this page

`?info` : view the info page

`?prefix <new prefix>` : change the prefix

`?upload <name>` : upload an MP3 or OGG to the name (will guide you through the process)

`?play <name>` : play back a saved sound

`?list` : view all sounds saved

`?delete <name>` : delete a sound

All commands can be prefixed with a mention, e.g `@{} help`
        '''.format(self.user.name)
        )
        await message.channel.send(embed=embed)


    async def info(self, message, stripped):
        em = discord.Embed(title='INFO', description=
        '''\u200B
  Default prefix: `?`
  Reset prefix: `@{user} prefix ?`
  Help: `{p}help`

  **Welcome to SFX!**
  Developer: <@203532103185465344>
  Find me on https://discord.gg/WQVaYmT and on https://github.com/JellyWX :)

  Framework: `discord.py`
  Total SᵒᵘʳᶜᵉLᶦⁿᵉˢOᶠCᵒᵈᵉ: {sloc} (100% Python)
  Hosting provider: OVH

  *If you have enquiries about new features, please send to the discord server*
  *If you have enquiries about bot development for you or your server, please DM me*
        '''.format(user=self.user.name, p=self.get_server(message.guild).prefix, sloc=sloccount_py('.'))
        )

        await message.channel.send(embed=em)

        await message.add_reaction('📬')


    async def wait_for_file(self, message, stripped):
        stripped = stripped.lower()
        server = self.get_server(message.guild)

        if len(server.sounds) >= 15 and stripped not in server.sounds.keys():
            await message.channel.send('Sorry, but the maximum is 15 sounds per server. You can either overwrite an existing sound name or use `{}delete` to remove a sound.')

        elif stripped == '':
            await message.channel.send('Please provide a name for your sound.')

        elif len(stripped) > 20:
            await message.channel.send('Please keep your names concise. You used {}/20 characters.'.format(len(stripped)))

        else:
            await message.channel.send('Saving as: `{}`. Send an MP3/OGG file <500KB or send any other message to cancel.'.format(stripped))

            msg = await self.wait_for('message', check=lambda x: x.author == message.author and x.channel == message.channel)

            if msg.attachments == [] or not msg.attachments[0].filename.endswith(('mp3', 'ogg')):
                await message.channel.send('Please attach an MP3/OGG file following the `{}upload` command. Aborted.'.format(server.prefix))

            elif msg.attachments[0].size > 500000:
                await message.channel.send('Please only send MP3/OGG files that are under 500KB. If your file is an MP3, consider turning it to an OGG for more optimized file size.')

            else:
                async with aiohttp.ClientSession() as cs:
                    async with cs.get(msg.attachments[0].url) as request:
                        mime = magic.from_buffer(await request.read(), mime=True)

                if mime in ['audio/mpeg', 'audio/ogg']:
                    server.sounds[stripped] = msg.attachments[0].url
                    await message.channel.send('Sound saved as `{name}`! Use `{prefix}play {name}` to play the sound.'.format(name=stripped, prefix=server.prefix))
                else:
                    await message.channel.send('Nice try. Please only upload MP3s or OGGs. If you *did* upload an MP3, it is likely corrupted or encoded wrongly.')


    async def play(self, message, stripped):
        stripped = stripped.lower()
        server = self.get_server(message.guild)

        if message.author.voice is None:
            await message.channel.send('You aren\'t in a voice channel.')

        elif stripped == '':
            await message.channel.send('You must specify the sound you wish to play. Use `{}list` to view all sounds.'.format(server.prefix))

        elif stripped not in server.sounds.keys():
            await message.channel.send('Sound `{}` could not be found. Use `{}list` to view all sounds'.format(stripped, server.prefix))

        else:
            try:
                voice = await message.author.voice.channel.connect()
            except discord.errors.ClientException:
                voice = [v for v in self.voice_clients if v.channel.guild == message.guild][0]
                if voice.channel != message.author.voice.channel:
                    await voice.disconnect()
                    voice = await message.author.voice.channel.connect()

            if voice.is_playing():
                voice.stop()

            voice.play(discord.FFmpegPCMAudio(server.sounds[stripped]))


    async def debug_play(self, message, stripped):
        try:
            voice = await message.author.voice.channel.connect()
        except discord.errors.ClientException:
            voice = [v for v in self.voice_clients if v.channel.guild == message.guild][0]

        if voice.is_playing():
            voice.stop()

        voice.play(discord.FFmpegPCMAudio(stripped))


    async def list(self, message, stripped):
        server = self.get_server(message.guild)

        await message.channel.send('All sounds on server: {}'.format(', '.join(server.sounds.keys())))


    async def delete(self, message, stripped):
        stripped = stripped.lower()
        server = self.get_server(message.guild)

        if stripped in server.sounds.keys():
            del server.sounds[stripped]
            await message.channel.send('Deleted `{}`. You have used {}/15 sounds.'.format(stripped, len(server.sounds)))
        else:
            await message.channel.send('Couldn\'t find sound by name {}. Use `{}list` to view all sounds.'.format(stripped, server.prefix))


try: ## token grabbing code
    with open('token','r') as token_f:
        token = token_f.read().strip('\n')

except:
    print('no token provided')
    sys.exit(-1)

client = BotClient()
client.run(token)
