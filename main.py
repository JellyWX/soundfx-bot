from models import Server, session, User, Sound

from ctypes.util import find_library
import discord ## pip3 install git+...
import sys
import os
import aiohttp ## pip3 install aiohttp
import magic ## pip3 install python-magic
import asyncio
import json
import time
from configparser import SafeConfigParser
from datetime import datetime
import traceback

from sqlalchemy.sql.expression import func


class BotClient(discord.AutoShardedClient):
    def __init__(self, *args, **kwargs):
        super(BotClient, self).__init__(*args, **kwargs)

        self.color = 0xff3838

        self.MAX_SOUNDS = 5

        self.commands = {
            'ping' : self.ping,
            'help' : self.help,
            'info': self.info,
            'prefix' : self.change_prefix,
            'upload' : self.wait_for_file,
            'play' : self.play,
            'list' : self.list,
            'delete' : self.delete,
            'stop' : self.stop,
            'link' : self.link,
            'unlink' : self.unlink,
            'soundboard' : self.soundboard,
            'more' : self.more,
            'roles' : self.role,
            'public' : self.public,
            'find' : self.find,
            'search' : self.search,
            'new' : self.search,
            'popular' : self.search,
            'random' : self.search,
            'report' : self.report,
            'greet' : self.greet,
            'review' : self.review
        }

        self.timeouts = {}

        self.config = SafeConfigParser()
        self.config.read('config.ini')

        self.force_download = self.config.get('DEFAULT', 'FORCE_DOWNLOAD').lower() == 'yes'

        if self.force_download and 'SOUNDS' not in os.listdir():
            os.mkdir('SOUNDS')

        self.cache_length = int(self.config.get('DEFAULT', 'CACHE_LENGTH'))

        self.trusted_ids = self.config.get('DEFAULT', 'TRUSTED_IDS').replace(' ', '').split(',')


    async def get_sounds(self, u):
        extra = 0

        user = session.query(User).filter(User.id == u.id).first()
        patreon_server = self.get_guild( int(self.config.get('DEFAULT', 'patreon_server')) )

        members = [p.id for p in patreon_server.members if not p.bot]

        if u.id in members:
            extra += 3

        if user.last_vote + 2592000 > time.time():
            extra += 5

        return self.MAX_SOUNDS + extra


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

        await self.leave_cleanup()


    async def welcome(self, guild, *args):
        if isinstance(guild, discord.Message):
            guild = guild.guild

        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages and not channel.is_nsfw():
                await channel.send('Thank you for adding SoundFX! To begin, type `?info` to learn more.')
                break
            else:
                continue


    def delete_sound(self, s):
        u = session.query(User).filter(User.join_sound_id == s.first().id)
        for user in u:
            print('resetting join sound for {}'.format(user.id))
            user.join_sound = None
            user.join_sound_id = None

        s.delete(synchronize_session='fetch')


    async def leave_cleanup(self, *args):
        all_ids = [g.id for g in self.guilds]

        servers = session.query(Server).filter(Server.id.notin_(all_ids))

        for s in servers:
            s_ids = [x.id for x in s.sounds]
            print(s_ids)

            u = session.query(User).filter(User.join_sound_id.in_(s_ids))
            for user in u:
                print('resetting join sound')
                user.join_sound = None
                user.join_sound_id = None

            s.sounds.delete(synchronize_session='fetch')

        servers.delete(synchronize_session='fetch')

        all_members = [m.id for m in self.get_all_members()]

        users = session.query(User).filter(User.id.notin_(all_members))

        users.delete(synchronize_session='fetch')

        session.commit()


    async def on_raw_reaction_add(self, payload):
        server = session.query(Server).filter_by(id=payload.guild_id).first()

        channel = self.get_channel(payload.channel_id)

        if channel.guild is None:
            return

        message = await channel.get_message(payload.message_id)
        user = channel.guild.get_member(payload.user_id)

        if message.embeds == []:
            return

        if user.bot or user.voice is None:
            return

        if message.author == self.user:
            r = None
            s = None
            done = False

            for reaction in message.reactions:

                if reaction.emoji == payload.emoji.name:

                    for sound in server.sounds:
                        if sound.emoji == reaction.emoji:
                            r = reaction
                            s = sound
                            done = True
                            break
                    else:
                        return

                elif done:
                    break

            if done:
                await message.remove_reaction(reaction, user)
                await message.add_reaction(reaction.emoji)

                await self.play_sound(message.guild, message.channel, user, s, server)


    async def on_voice_state_update(self, member, before, after):
        user = session.query(User).filter(User.id == member.id).first()
        server = session.query(Server).filter_by(id=member.guild.id).first()

        if user is None:
            return

        elif before.channel != after.channel and after.channel is not None \
            and user.join_sound is not None:

            if user.join_sound.public:

                await self.play_sound(member.guild, member, member, user.join_sound, server)
                print('Playing join sound')

            else:
                user.join_sound = None

        elif before.channel is not None and after.channel is None \
            and user.leave_sound is not None:

            if user.leave_sound.public:

                await self.play_sound(member.guild, member, member, user.leave_sound, server)
                print('Playing leave sound')
            else:
                user.leave_sound = None


    async def on_message(self, message):

        if isinstance(message.channel, discord.DMChannel) or message.author.bot or message.content is None:
            return

        if session.query(Server).filter_by(id=message.guild.id).first() is None:
            s = Server(id=message.guild.id, prefix='?', roles=['off'])
            session.add(s)
            session.commit()

        if session.query(User).filter_by(id=message.author.id).first() is None:
            s = User(id=message.author.id, last_vote=0)
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
            self.timeouts[message.guild.id] = time.time()

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
        embed = discord.Embed(title='HELP', color=self.color, description=
        '''
**This help page doesn't work on mobile.**
`?info` : view the info page

`?more` : view how many sounds you have

`?prefix <new prefix>` : change the prefix

`?roles` : set the roles that can use the bot

`?upload <name>` : upload an MP3 or OGG to the name (will guide you through the process)

`?play <name>` : play a saved sound, or look for public sounds with the name provided
`?play ID:<id>` : play a public sound by ID
`?<soundname>` : alternative to `?play <name>`. Only works for sounds in your server.

`?stop` : disconnect the bot from voice

`?list` : view all sounds saved

`?delete <name>` : delete a sound

`?public <name>` : set a sound to public/private

`?search <term>` : search for public sounds and get IDs

`?new` `?popular` `?random` : find new sound effects from the Repository

`?report <ID>` : report a public sound by ID for advertising or hate

`?greet <ID>` : set your greeting sound (plays when you join a VC) (sound must be public)

All commands can be prefixed with a mention, e.g `@{} help`
        '''.format(self.user.name)
        )
        await message.channel.send(embed=embed)


    async def info(self, message, stripped, server):
        em = discord.Embed(title='INFO', color=self.color, description=
        '''\u200B
  Default prefix: `?`
  Reset prefix: `@{user} prefix ?`
  Help: `{p}help`
  **Welcome to SFX!**
  Developer: <@203532103185465344>
  Find me on https://discord.gg/v6YMfjj and on https://github.com/JellyWX :)
  Framework: `discord.py`
  Hosting provider: OVH
  There is a maximum sound limit per server. You can view this through `{p}more`
  *If you have enquiries about new features, please send to the discord server*
  *If you have enquiries about bot development for you or your server, please DM me*
        '''.format(user=self.user.name, p=server.prefix)
        )

        await message.channel.send(embed=em)

        await message.add_reaction('📬')


    async def more(self, message, stripped, server):

        user = session.query(User).filter(User.id == message.author.id).first()

        em = discord.Embed(title='MORE', description=
        '''
You have {} sounds (using {})
2 ways you can get more sounds for you:
    - Join our server to keep up on the latest! https://discord.gg/v6YMfjj You will get **three** extra sounds
    - Upvote our bot over on https://discordbots.org/bot/430384808200372245 You will get **five** extra sounds
        '''.format(await self.get_sounds(message.author), len(user.sounds)))

        await message.channel.send(embed=em)


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


    async def cleanup(self):
        await self.wait_until_ready()
        while not client.is_closed():
            ids = []

            for guild_id, last_time in self.timeouts.copy().items():
                if time.time() - 300 >= last_time:
                    ids.append(guild_id)
                    del self.timeouts[guild_id]

            for vc in self.voice_clients:
                if len([m for m in vc.channel.members if not m.bot]) == 0 or vc.channel.guild.id in ids:
                    await vc.disconnect()

            for f in os.listdir('SOUNDS'):
                s = session.query(Sound).filter(Sound.id == int(f)).first()

                if s is None or (s.last_used is not None and s.last_used + self.cache_length <= time.time()):
                    os.remove('SOUNDS/{}'.format(f))

            await asyncio.sleep(15)


    async def wait_for_file(self, message, stripped, server):
        stripped = stripped.lower()

        if 'off' not in server.roles and not message.author.guild_permissions.manage_guild:
            for role in message.author.roles:
                if role.id in server.roles:
                    break
            else:
                await message.channel.send('You aren\'t allowed to do this. Please tell a moderator to do `{}roles` to set up permissions'.format(server.prefix))
                return

        premium = False

        async with aiohttp.ClientSession() as cs:
            async with cs.get('https://fusiondiscordbots.com/api/user/subscriptions/{}'.format(message.author.id)) as request:
                t = await request.read()
                if 'soundfx' in str(t):
                    premium = True


        user = session.query(User).filter(User.id == message.author.id).first()

        print()

        if len(user.sounds) >= await self.get_sounds(message.author) and not premium:
            await message.channel.send('Sorry, but the maximum is {} sounds per user (+{} for your bonuses). You can either use `{prefix}delete` to remove a sound or type `{prefix}more` to learn ways to get more sounds! https://discord.gg/v6YMfjj'.format(self.MAX_SOUNDS, await self.get_sounds(message.author) - self.MAX_SOUNDS, prefix=server.prefix))

        elif stripped == '':
            await message.channel.send('Please provide a name for your sound in the command, e.g `?upload TERMINATION`')

        elif all( [x in '0123456789' for x in stripped] ):
            await message.channel.send('Please use at least one non-numerical character in your sound\'s name (this helps distunguish it from IDs)')

        elif len(stripped) > 20:
            await message.channel.send('Please keep your names concise. You used {}/20 characters.'.format(len(stripped)))

        else:
            sound = session.query(Sound).filter(Sound.server_id == message.guild.id).filter(Sound.name == stripped)
            s = sound.first()

            await message.channel.send('Saving as: `{}`. Send an MP3/OGG file <500KB (1MB for premium users) or send any other message to cancel.'.format(stripped))

            msg = await self.wait_for('message', check=lambda x: x.author == message.author and x.channel == message.channel)

            if msg.attachments == [] or not msg.attachments[0].filename.lower().endswith(('mp3', 'ogg')):
                await message.channel.send('Please attach an MP3/OGG file following the `{}upload` command. Aborted.'.format(server.prefix))

            elif (msg.attachments[0].size > 500000 and not premium) or (msg.attachments[0].size > 1000000 and premium):
                await message.channel.send('Please only send MP3/OGG files that are under 500KB (1MB if premium user). If your file is an MP3, consider turning it to an OGG for more optimized file size.')

            else:
                async with aiohttp.ClientSession() as cs:
                    async with cs.get(msg.attachments[0].url) as request:
                        mime = magic.from_buffer(await request.read(), mime=True)

                if mime in ['audio/mpeg', 'audio/ogg']:

                    if s is not None:
                        self.delete_sound(sound)

                    sound = Sound(url=msg.attachments[0].url, server=server, user=user, name=stripped, plays=0, reports=0)

                    session.add(sound)

                    response = await message.channel.send('Sound saved as `{name}`! Use `{prefix}play {name}` to play the sound. **Please do not delete the file from discord.**'.format(name=stripped, prefix=server.prefix))

                else:
                    await message.channel.send('Please only upload MP3s or OGGs. If you *did* upload an MP3, it is likely corrupted or encoded wrongly. To resolve, visit https://audio.online-convert.com/convert-to-ogg and convert your file to an OGG.'.format(mime))


    async def play(self, message, stripped, server):
        stripped = stripped.lower()

        if stripped.startswith('id:') and all( [x in '0123456789' for x in stripped[3:]] ) :
            id = int( stripped[3:] )
            s = session.query(Sound).filter(Sound.public).filter(Sound.id == id).first()

            if s is None:
                await message.channel.send('No sound found by ID')
                return

        else:
            s = session.query(Sound).filter_by(server_id=message.guild.id, name=stripped).first()

        if stripped == '':
            await message.channel.send('You must specify the sound you wish to play. Use `{}list` to view all sounds.'.format(server.prefix))

        elif s is None: ## if none in current server by name:
            sq = session.query(Sound).filter( Sound.public ).filter( Sound.name == stripped ).order_by( func.rand() ) ## query by name
            s = sq.first()

            if sq.count() > 1:

                await message.channel.send('Mutiple sounds with name specified. Consider using `{}play ID:1234` to specify an ID. Playing {} (ID {}) from {}...'.format( server.prefix, s.name, s.id, self.get_guild(s.server_id).name ))

                await self.play_sound(message.guild, message.channel, message.author, s, server)

            elif sq.count() == 0:

                await message.channel.send('Sound `{0}` could not be found in server or in Sound Repository by name. Use `{1}list` to view all sounds, `{1}search` to search for public sounds, or `{1}play ID:1234` to play a sound by ID'.format(stripped, server.prefix))

            else:
                await message.channel.send('Playing public sound {name} (ID {id}) from {guild}. Use `{pref}report {id}` if this sound is inappropriate'.format(
                    name = s.name,
                    id = s.id,
                    guild = self.get_guild(s.server_id).name,
                    pref = server.prefix
                    )
                )

                await self.play_sound(message.guild, message.channel, message.author, s, server)

        else:
            await self.play_sound(message.guild, message.channel, message.author, s, server)


    async def stop(self, message, stripped, server):

        voice = [v for v in self.voice_clients if v.channel.guild == message.guild]
        if len(voice) == 0:
            await message.channel.send('Not connected to a VC!')
        else:
            await voice[0].disconnect()


    async def play_sound(self, guild, channel, caller, sound, server):
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
            try:
                voice = await caller.voice.channel.connect()
            except discord.errors.ClientException:
                voice = [v for v in self.voice_clients if v.channel.guild == guild][0]
                if voice.channel != caller.voice.channel:
                    await voice.disconnect()
                    voice = await caller.voice.channel.connect()

            if voice.is_playing():
                voice.stop()

            if self.force_download:
                downloaded = [int(f) for f in os.listdir('SOUNDS')]

                if sound.id in downloaded:
                    print('Sound cached, playing from file...')

                else:
                    print('Sound not cached, attempting to cache...')

                    async with aiohttp.ClientSession() as csession:
                        async with csession.get(sound.url) as resp:
                            if resp.status != 200:
                                await channel.send('Sound file couldn\'t be loaded. Try again later, or consider re-uploading it. This can happen if the file is deleted or permission levels change.')
                                return

                            t = await resp.read()

                            with open('SOUNDS/{}'.format(sound.id), 'wb') as f:
                                f.write(t)

                voice.play(discord.FFmpegPCMAudio('SOUNDS/{}'.format(sound.id)))

            else:
                print('Consider enabling force download in config.ini')
                voice.play(discord.FFmpegPCMAudio(sound.url))

            sound.last_used = time.time()

            if sound.plays is None:
                sound.plays = 1
            else:
                sound.plays += 1


    async def list(self, message, stripped, server):

        strings = []
        for s in server.sounds:
            string = '**{}**'.format(s.name)
            if s.public:
                string += ' (\U0001F513)'
            else:
                string += ' (\U0001F510)'

            if s.emoji is None:
                pass
            elif isinstance(s.emoji, str):
                string += ' ({})'.format(s.emoji)
            else:
                string += ' (<:{0}:{1}>)'.format(s.emoji, s.emoji_id)

            strings.append(string)

        await message.channel.send('All sounds on server: {}'.format(', '.join(strings)))


    async def link(self, message, stripped, server):
        stripped = stripped.lower()

        s = server.sounds.filter(Sound.name == stripped).first()

        if stripped == '':
            await message.channel.send('Please provide the name of the sound you wish to link to an emoji (e.g `?link HEADHUNTER`)')

        elif s is not None:
            response = await message.channel.send('Found sound. Please react to this message with the emoji you wish to use!')

            try:
                reaction, _ = await client.wait_for('reaction_add', timeout=120, check=lambda r, u: r.message.id == response.id and u == message.author)
            except:
                pass

            if isinstance(reaction.emoji, discord.Emoji):
                await message.channel.send('Please only use normal emojis.')

            else:
                s.emoji = reaction.emoji

                await message.channel.send('Reaction attached. Do `?soundboard` to open the soundboard.')

        else:
            await message.channel.send('Couldn\'t find sound by name `{}`!'.format(stripped))


    async def unlink(self, message, stripped, server):
        stripped = stripped.lower()

        s = server.sounds.filter(Sound.name == stripped).first()

        if stripped == '':
            await message.channel.send('Please provide the name of the sound you wish to unlink from its emoji (e.g `?unlink ULTRAKILL`)')

        elif s is not None:
            s.emoji = None
            s.emoji_id = None
            await message.channel.send('Unlinked `{}`'.format(stripped))

        else:
            await message.channel.send('Couldn\'t find sound by name `{}`!'.format(stripped))


    async def delete(self, message, stripped, server):
        stripped = stripped.lower()

        s = server.sounds.filter(Sound.name == stripped)

        user = session.query(User).filter(User.id == message.author.id).first()

        if 'off' not in server.roles and not message.author.guild_permissions.manage_guild:
            for role in message.author.roles:
                if role.id in server.roles:
                    break
            else:
                await message.channel.send('You aren\'t allowed to do this. Please tell a moderator to do `{}roles` to set up permissions'.format(server.prefix))
                return

        if s.first() is not None:
            self.delete_sound(s)
            await message.channel.send('Deleted `{}`. You have used {}/{} sounds.'.format(stripped, len(user.sounds), await self.get_sounds(message.author)))
        else:
            await message.channel.send('Couldn\'t find sound by name {}. Use `{}list` to view all sounds.'.format(stripped, server.prefix))


    async def soundboard(self, message, stripped, server):

        strings = []
        emojis = []

        for sounds in server.sounds.filter(Sound.emoji is not None):

            strings.append('`{}` : {}'.format(sounds.name, sounds.emoji))
            emojis.append(sounds.emoji)

        m = await message.channel.send(embed=discord.Embed(color=self.color, description='\n\n'.join(strings)))
        for e in emojis:
            await m.add_reaction(e)


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
            if s.locked:
                await message.channel.send('This sound has been locked due to inappropriate content. Your server can still use it, but it cannot go public. If you have an issue with this, please come talk to us (in a civil manner) at our discord.')
                return

            s.public = not s.public
            await message.channel.send('Sound `{}` has been set to {}.'.format(stripped, 'public \U0001F513' if s.public else 'private \U0001F510'))
        else:
            await message.channel.send('Couldn\'t find sound by name {}. Use `{}list` to view all sounds.'.format(stripped, server.prefix))


    async def find(self, message, *args):
        await message.channel.send('`find` has been built into `play`. Please do `play ID:1234`')


    async def search(self, message, stripped, server):

        embed = discord.Embed(title='Public sounds matching filter:')

        length = 0

        if 'new' in message.content.split(' ')[0]:
            for sound in session.query(Sound).filter(Sound.public).order_by(Sound.id.desc()):
                if length < 1650:
                    content = 'ID: {}\nGuild: {}'.format(sound.id, self.get_guild(sound.server_id).name)

                    embed.add_field(name=sound.name, value=content, inline=True)

                    length += len(content) + len(sound.name)

        elif 'popular' in message.content.split(' ')[0]:
            for sound in session.query(Sound).filter(Sound.public).order_by(Sound.plays.desc()):
                if length < 1650:
                    content = 'ID: {}\nPlays: {}'.format(sound.id, sound.plays)

                    embed.add_field(name=sound.name, value=content, inline=True)

                    length += len(content) + len(sound.name)

        elif 'random' in message.content.split(' ')[0]:
            for sound in session.query(Sound).filter(Sound.public).order_by(func.rand()):
                if length < 1650:
                    content = 'ID: {}\nGuild: {}'.format(sound.id, self.get_guild(sound.server_id).name)

                    embed.add_field(name=sound.name, value=content, inline=True)

                    length += len(content) + len(sound.name)

        else:
            for sound in session.query(Sound).filter(Sound.public).filter(Sound.name.ilike('%{}%'.format(stripped))):
                if length < 1650:
                    content = 'ID: {}\nGuild: {}'.format(sound.id, self.get_guild(sound.server_id).name)

                    embed.add_field(name=sound.name, value=content, inline=True)

                    length += len(content) + len(sound.name)

                else:
                    embed.set_footer(text='More results were found, but removed due to size restrictions')
                    break

        await message.channel.send(embed=embed)


    async def report(self, message, stripped, server):
        stripped = stripped.lower()

        if all([x in '0123456789' for x in stripped]):
            id = int( stripped )

            sound = session.query(Sound).filter(Sound.public).filter(Sound.id == id).first()

            if sound is not None:
                if sound.reports is None:
                    sound.reports = 1
                else:
                    sound.reports += 1
                await message.channel.send('The sound has been reported and will be reviewed. Thank you.')
            else:
                await message.channel.send('No sound found with ID {}'.format(id))

        else:
            await message.channel.send('Please specify a numerical ID. You can find IDs using the search command.')


    async def greet(self, message, stripped, server):
        user = session.query(User).filter(User.id == message.author.id).first()
        stripped = stripped.lower()

        if stripped == '' and user.join_sound is not None:
            user.join_sound = None
            await message.channel.send('You have unassigned your greet sound')

        elif stripped == '':
            await message.channel.send('Please specify a numerical ID. You can find IDs using the search command.')

        elif all([x in '0123456789' for x in stripped]):
            id = int( stripped )

            sound = session.query(Sound).filter(Sound.public).filter(Sound.id == id).first()

            if user is None:
                user = User(id=message.author.id, last_vote=0, join_sound=None, leave_sound=None)
                session.add(user)
                session.commit()

            if sound is not None:
                user.join_sound = sound
                await message.channel.send('Your greet sound has been set.')

            else:
                await message.channel.send('No public sound found with ID {}'.format(id))

        else:
            await message.channel.send('Please specify a numerical ID. You can find IDs using the search command.')


    async def review(self, message, stripped, server):
        if str(message.author.id) not in self.trusted_ids:
            return

        s = session.query(Sound).filter_by(safe=False, public=True).order_by(Sound.reports.desc()).first()

        await message.channel.send('Current sound: {} (guild: {}, reports: {}). Type \'safe\' or \'lock\' to issue justice'.format(s.name, self.get_guild(s.server_id).name, s.reports))
        await self.play_sound(message.guild, message.channel, message.author, s, server)

        m = await self.wait_for('message', check=lambda x: x.author == message.author and x.channel == message.channel)

        if m.content == 'lock':
            s.locked = True
            s.public = False
            await message.channel.send('Sound has been locked.')

        elif m.content == 'safe':
            s.safe = True
            await message.channel.send('Sound has been set as safe.')

        else:
            await message.channel.send('Judgement postponed.')


client = BotClient()

try:

    client.loop.create_task(client.cleanup())
    client.run(client.config.get('TOKENS', 'bot'))
except Exception as e:
    print('Error detected. Restarting in 15 seconds.')
    print(sys.exc_info())
    time.sleep(15)

    os.execl(sys.executable, sys.executable, *sys.argv)
