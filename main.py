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
import asyncio
import json


class BotClient(discord.Client):
    def __init__(self, *args, **kwargs):
        super(BotClient, self).__init__(*args, **kwargs)
        self.get_server = lambda x: [d for d in self.data if d.id == x.id][0]

        self.data = []
        self.color = 0xff3838

        self.commands = {
            'ping' : self.ping,
            'help' : self.help,
            'info': self.info,
            'prefix' : self.change_prefix,
            'upload' : self.wait_for_file,
            'play' : self.play,
            'list' : self.list,
            'delete' : self.delete,
            'debug' : self.debug_play,
            'stop' : self.stop,
            'link' : self.link,
            'unlink' : self.unlink,
            'soundboard' : self.soundboard,
            'data' : self.get_data,
            'more' : self.more
        }

        with open('tokens.json', 'r') as f:
            self.tokens = json.load(f)

        with open('settings.json', 'r') as f:
            self.settings = json.load(f)

        try:
            with open('data.mp', 'rb') as f:
                for d in msgpack.unpackb(zlib.decompress(f.read()), encoding='utf8'):
                    self.data.append(ServerData(**d))
        except FileNotFoundError:
            pass


    async def get_sounds(self, guild):
        base = 14
        extra = 0

        patreon_server = self.get_guild(self.settings['patreon_server'])
        members = [p.id for p in patreon_server.members if not p.bot]

        voters = await self.get_voters()

        for member in guild.members:
            if member.id in members:
                extra += 1

            if member.id in voters:
                extra += 2

        return base + extra


    async def get_voters(self):
        async with aiohttp.ClientSession() as session:
            async with session.get('https://discordbots.org/api/bots/votes', headers={'authorization' : self.tokens['discordbots'], 'content-type' : 'application/json'}) as resp:
                return [int(x['id']) for x in json.loads(await resp.text())]


    async def send(self):
        guild_count = len(self.guilds)
        member_count = len([x for x in self.get_all_members()])

        if self.tokens['discordbots']:

            session = aiohttp.ClientSession()
            dump = json.dumps({
                'server_count': len(client.guilds)
            })

            head = {
                'authorization': self.tokens['discordbots'],
                'content-type' : 'application/json'
            }

            url = 'https://discordbots.org/api/bots/stats'
            async with session.post(url, data=dump, headers=head) as resp:
                print('returned {0.status} for {1}'.format(resp, dump))

            session.close()

        async with aiohttp.ClientSession() as session:
            async with session.post('https://api.fusiondiscordbots.com/{}/'.format(self.user.id), data={'token' : self.tokens['fusion'], 'guilds' : guild_count, 'members' : member_count}) as resp:
                print('returned {0.status} from api.fusiondiscordbots.com'.format(resp))


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
        await self.send()


    async def on_guild_remove(self, guild):
        self.data = [d for d in self.data if d.id != guild.id]
        await self.send()


    async def on_reaction_add(self, reaction, user):
        if reaction.message.guild is None:
            return

        if user.bot or user.voice is None:
            return

        if reaction.message.author == self.user:
            if isinstance(reaction.emoji, discord.Emoji):
                for stripped, data in self.get_server(reaction.message.guild).sounds.items():
                    if data['emoji'] is not None and (not isinstance(data['emoji'], str)) and data['emoji'][1] == reaction.emoji.id:
                        break # the combination of this break and the else following quits the flow if the reaction isnt stored for use
                else:
                    return

            else:
                for stripped, data in self.get_server(reaction.message.guild).sounds.items():
                    if data['emoji'] == reaction.emoji:
                        break
                else:
                    return

            # method continues here
            await reaction.message.remove_reaction(reaction, user)
            await reaction.message.add_reaction(reaction.emoji)

            try:
                voice = await user.voice.channel.connect()
            except discord.errors.ClientException:
                voice = [v for v in self.voice_clients if v.channel.guild == reaction.message.guild][0]
                if voice.channel != user.voice.channel:
                    await voice.disconnect()
                    voice = await user.voice.channel.connect()

            if voice.is_playing():
                voice.stop()

            voice.play(discord.FFmpegPCMAudio(data['url']))


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

        try:
            if await self.get_cmd(message):
                with open('data.mp', 'wb') as f:
                    print('data stored')
                    f.write(zlib.compress(msgpack.packb([d.__dict__ for d in self.data])))
        except Exception as e:
            print(e)
            await message.channel.send('Internal exception detected in command, {}'.format(e))


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
        embed = discord.Embed(title='HELP', color=self.color, description=
        '''
`?help` : view this page

`?info` : view the info page

`?prefix <new prefix>` : change the prefix

`?upload <name>` : upload an MP3 or OGG to the name (will guide you through the process)

`?play <name>` : play back a saved sound

`?list` : view all sounds saved

`?delete <name>` : delete a sound

`?stop` : disconnect the bot from voice

`?link <name>` : link a reaction to a sound

`?unlink <name>` : unlink a sound-reaction pair

`?soundboard` : pull up all sounds with reaction pairs

All commands can be prefixed with a mention, e.g `@{} help`
        '''.format(self.user.name)
        )
        await message.channel.send(embed=embed)


    async def info(self, message, stripped):
        em = discord.Embed(title='INFO', color=self.color, description=
        '''\u200B
  Default prefix: `?`
  Reset prefix: `@{user} prefix ?`
  Help: `{p}help`

  **Welcome to SFX!**
  Developer: <@203532103185465344>
  Find me on https://discord.gg/SmCPXn2 and on https://github.com/JellyWX :)

  Framework: `discord.py`
  Total SᵒᵘʳᶜᵉLᶦⁿᵉˢOᶠCᵒᵈᵉ: {sloc} (100% Python)
  Hosting provider: OVH

  *If you have enquiries about new features, please send to the discord server*
  *If you have enquiries about bot development for you or your server, please DM me*

  In accordance with data protection, we only store the bare necessities. To view data stored about your server, you can run `?data`
        '''.format(user=self.user.name, p=self.get_server(message.guild).prefix, sloc=sloccount_py('.'))
        )

        await message.channel.send(embed=em)

        await message.add_reaction('📬')


    async def more(self, message, stripped):
        em = discord.Embed(title='MORE', description=
        '''
2 ways you can get more sounds for your Discord server:

    - Join our server to keep up on the latest! https://discord.gg/SmCPXn2 You will get **one** extra sound for each member that joins the server

    - Upvote our bot over on https://discordbots.org/bot/430384808200372245 You will get **two** extra sounds for each member that upvotes the bot
        ''')

        await message.channel.send(embed=em)


    async def cleanup(self):
        await self.wait_until_ready()
        while not client.is_closed():
            for vc in self.voice_clients:
                if len([m for m in vc.channel.members if not m.bot]) == 0:
                    await vc.disconnect()

            await asyncio.sleep(15)


    async def wait_for_file(self, message, stripped):
        stripped = stripped.lower()
        server = self.get_server(message.guild)

        if len(server.sounds) >= await self.get_sounds(message.guild) and stripped not in server.sounds.keys():
            await message.channel.send('Sorry, but the maximum is 14 sounds per server (+{} for your server bonuses). You can either overwrite an existing sound name, use `{prefix}delete` to remove a sound or type `{prefix}more` to learn more ways to get sounds! https://discord.gg/SmCPXn2'.format(await self.get_sounds(message.guild) - 14, prefix=server.prefix))

        elif stripped == '':
            await message.channel.send('Please provide a name for your sound in the command, e.g `?upload TERMINATION`')

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
                    server.sounds[stripped] = {'url' : msg.attachments[0].url, 'emoji' : None}
                    response = await message.channel.send('Sound saved as `{name}`! Use `{prefix}play {name}` to play the sound. If you want to add a reaction binding, react to this message within 30 seconds. Please do not delete the file from discord.'.format(name=stripped, prefix=server.prefix))

                    try:
                        reaction, _ = await client.wait_for('reaction_add', timeout=30, check=lambda r, u: r.message.id == response.id and u == message.author)
                    except:
                        pass
                    else:
                        if isinstance(reaction.emoji, discord.Emoji):
                            if reaction.emoji.animated:
                                server.sounds[stripped]['emoji'] = ('a:' + reaction.emoji.name, reaction.emoji.id)
                            else:
                                server.sounds[stripped]['emoji'] = (reaction.emoji.name, reaction.emoji.id)
                        else:
                            server.sounds[stripped]['emoji'] = reaction.emoji

                        await message.channel.send('Reaction attached! React to any of my messages to bring up the sound.')

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

            voice.play(discord.FFmpegPCMAudio(server.sounds[stripped]['url']))


    async def stop(self, message, stripped):
        server = self.get_server(message.guild)

        voice = [v for v in self.voice_clients if v.channel.guild == message.guild]
        if len(voice) == 0:
            await message.channel.send('Not connected to a VC!')
        else:
            await voice[0].disconnect()


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

        strings = []
        for name, data in server.sounds.items():
            string = name
            if data['emoji'] is None:
                pass
            elif isinstance(data['emoji'], str):
                string += ' ({})'.format(data['emoji'])
            else:
                string += ' (<:{0}:{1}>)'.format(*data['emoji'])

            strings.append(string)

        await message.channel.send('All sounds on server: {}'.format(', '.join(strings)))


    async def link(self, message, stripped):
        server = self.get_server(message.guild)
        stripped = stripped.lower()

        if stripped == '':
            await message.channel.send('Please provide the name of the sound you wish to link to an emoji (e.g `?link HEADHUNTER`)')

        elif stripped in server.sounds.keys():
            response = await message.channel.send('Found sound. Please react to this message with the emoji you wish to use!')

            try:
                reaction, _ = await client.wait_for('reaction_add', timeout=120, check=lambda r, u: r.message.id == response.id and u == message.author)
            except:
                pass

            if isinstance(reaction.emoji, discord.Emoji):
                if reaction.emoji.animated:
                    server.sounds[stripped]['emoji'] = ('a:' + reaction.emoji.name, reaction.emoji.id)
                else:
                    server.sounds[stripped]['emoji'] = (reaction.emoji.name, reaction.emoji.id)
            else:
                server.sounds[stripped]['emoji'] = reaction.emoji

            await message.channel.send('Reaction attached! React to any of my messages to bring up the sound.')

        else:
            await message.channel.send('Couldn\'t find sound by name `{}`!'.format(stripped))


    async def unlink(self, message, stripped):
        server = self.get_server(message.guild)
        stripped = stripped.lower()

        if stripped == '':
            await message.channel.send('Please provide the name of the sound you wish to unlink from its emoji (e.g `?unlink ULTRAKILL`)')

        elif stripped in server.sounds.keys():
            server.sounds[stripped]['emoji'] = None
            await message.channel.send('Unlinked `{}`'.format(stripped))

        else:
            await message.channel.send('Couldn\'t find sound by name `{}`!'.format(stripped))


    async def delete(self, message, stripped):
        stripped = stripped.lower()
        server = self.get_server(message.guild)

        if stripped in server.sounds.keys():
            del server.sounds[stripped]
            await message.channel.send('Deleted `{}`. You have used {}/{} sounds.'.format(stripped, len(server.sounds), await self.get_sounds(message.guild)))
        else:
            await message.channel.send('Couldn\'t find sound by name {}. Use `{}list` to view all sounds.'.format(stripped, server.prefix))


    async def soundboard(self, message, stripped):
        server = self.get_server(message.guild)

        strings = []
        emojis = []

        for name, data in server.sounds.items():
            if data['emoji'] is None:
                pass
            elif isinstance(data['emoji'], str):
                strings.append('`{}` : {}'.format(name, data['emoji']))
                emojis.append(data['emoji'])
            else:
                strings.append('`{}` : <:{}:{}>'.format(name, *data['emoji']))
                emojis.append(self.get_emoji(data['emoji'][1]))

        m = await message.channel.send(embed=discord.Embed(color=self.color, description='\n\n'.join(strings)))
        for e in emojis:
            await m.add_reaction(e)


    async def get_data(self, message, stripped):
        server = self.get_server(message.guild)

        with open('temp.json', 'w') as f:
            json.dump(server.__dict__, f)

        f = open('temp.json', 'r')
        await message.channel.send('Data has been converted to JSON format.', file=discord.File(f, 'data.json'))
        f.close()


client = BotClient()
client.loop.create_task(client.cleanup())
client.run(client.tokens['bot'])
