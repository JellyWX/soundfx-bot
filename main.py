import re

from models import GuildData, session, Sound
from config import config

from ctypes.util import find_library
import discord
import os
import typing
from enum import Enum
import aiohttp
import asyncio
import json
import traceback
import subprocess
import concurrent.futures
from functools import partial

from sqlalchemy.sql.expression import func


def check_digits(x: str) -> bool:
    return len(x) and all([y in '0123456789' for y in x])


class PermissionLevels(Enum):
    UNRESTRICTED = 0
    MANAGED = 1
    RESTRICTED = 2


class Command:
    def __init__(self, function_call: (discord.Message, str, GuildData), permission_level: PermissionLevels):
        self.func = function_call
        self.permission_level = permission_level

    async def call(self, caller: discord.Member, guild_data: GuildData, *args) -> typing.Optional[str]:
        if self.permission_level == PermissionLevels.UNRESTRICTED:
            await self._call_func(*args)

        elif self.permission_level == PermissionLevels.MANAGED:
            if self._check_managed_perms(caller, guild_data):
                await self._call_func(*args)
            else:
                return "You must have an appropriate role to run this command. Tell an admin to do `?roles`"

        elif self.permission_level == PermissionLevels.RESTRICTED:
            if caller.guild_permissions.manage_guild:
                await self._call_func(*args)
            else:
                return "You must be a guild manager to run this command"

    async def _call_func(self, *args):
        await self.func(*args)

    @staticmethod
    def _check_managed_perms(member: discord.Member, guild_data: GuildData) -> bool:
        if member.guild_permissions.manage_guild:
            return True

        elif len(guild_data.roles) > 0:
            for role in member.roles:
                if role.id in guild_data.roles:
                    return False
            else:
                return True

        else:
            return True


class BotClient(discord.AutoShardedClient):
    def __init__(self, *args, **kwargs):
        super(BotClient, self).__init__(*args, **kwargs)

        self.EMBED_COLOR = 0xFF3838

        self.file_indexing = 0

        self.commands = {
            'ping': Command(self.ping, PermissionLevels.UNRESTRICTED),
            'help': Command(self.help, PermissionLevels.UNRESTRICTED),
            'info': Command(self.info, PermissionLevels.UNRESTRICTED),
            'invite': Command(self.info, PermissionLevels.UNRESTRICTED),

            'upload': Command(self.wait_for_file, PermissionLevels.MANAGED),
            'delete': Command(self.delete, PermissionLevels.MANAGED),

            'play': Command(self.play, PermissionLevels.MANAGED),
            'p': Command(self.play, PermissionLevels.MANAGED),
            'stop': Command(self.stop, PermissionLevels.MANAGED),
            'volume': Command(self.volume, PermissionLevels.MANAGED),

            'prefix': Command(self.change_prefix, PermissionLevels.RESTRICTED),
            'roles': Command(self.role, PermissionLevels.RESTRICTED),

            'public': Command(self.public, PermissionLevels.MANAGED),

            'list': Command(self.list, PermissionLevels.UNRESTRICTED),
            'search': Command(self.search, PermissionLevels.UNRESTRICTED),
            'popular': Command(self.search, PermissionLevels.UNRESTRICTED),
            'random': Command(self.search, PermissionLevels.UNRESTRICTED),
        }

        self.aiohttp_session: typing.Optional[aiohttp.client.ClientSession] = None
        self.executor = concurrent.futures.ThreadPoolExecutor()

    @staticmethod
    def get_sound_by_string(string: str, server_id: int, uploader_id: int) -> typing.Optional[Sound]:
        r = re.match(r'(?:(?i)ID:)?(\d+)', string)

        if r is not None:
            return session.query(Sound).get(int(r.groups()[0]))

        else:
            q = session.query(Sound).filter(Sound.name == string.lower()) \
                .order_by(
                Sound.server_id != server_id,
                Sound.uploader_id != uploader_id,
                Sound.public == False,
                func.rand()) \
                .first()

            if q is None or (q.server_id != server_id and q.uploader_id != uploader_id and not q.public):
                return None

            else:
                return q

    async def do_blocking(self, method):
        a, _ = await asyncio.wait([self.loop.run_in_executor(self.executor, method)])
        return [x.result() for x in a][0]

    async def send(self):
        guild_count = len(self.guilds)

        if config.dbl_token is not None:
            dump = json.dumps({
                'server_count': guild_count
            })

            head = {
                'authorization': config.dbl_token,
                'content-type': 'application/json'
            }

            url = 'https://discordbots.org/api/bots/stats'
            async with self.aiohttp_session.post(url, data=dump, headers=head) as resp:
                print('returned {0.status} for {1}'.format(resp, dump))

    async def on_ready(self):
        discord.opus.load_opus(find_library('opus'))

        self.aiohttp_session = aiohttp.ClientSession()

        print('Logged in as')
        print(self.user.id)

    async def on_guild_join(self, guild):
        await self.send()

        await self.welcome(guild)

        self.update_guild_name(guild)

    async def on_guild_remove(self, _guild):
        await self.send()

    # noinspection PyMethodMayBeStatic
    async def on_guild_update(self, _before, after):
        self.update_guild_name(after)

    @staticmethod
    def update_guild_name(guild):
        g = session.query(GuildData).filter(GuildData.id == guild.id).first()

        if g is not None:
            g.name = guild.name

    @staticmethod
    async def welcome(guild, *_args):
        if isinstance(guild, discord.Message):
            guild = guild.guild

        for channel in guild.text_channels:
            if not channel.is_nsfw() and channel.permissions_for(guild.me).send_messages:
                await channel.send('Thank you for adding SoundFX! To begin, type `?info` to learn more.')
                break

    async def check_and_play(self, guild, channel, caller, sound, guild_data):
        if caller.voice is None:
            await channel.send("You aren't in a voice channel.")

        elif not caller.voice.channel.permissions_for(guild.me).connect:
            await channel.send('No permissions to connect to channel.')

        else:
            await self.play_sound(caller.voice.channel, sound, guild_data.volume)

    async def play_sound(self, v_c, sound, volume):
        perms = v_c.permissions_for(v_c.guild.me)

        if perms.connect and perms.speak:
            src = sound.src

            try:
                voice = await v_c.connect(timeout=5)
            except discord.errors.ClientException:
                voice = [v for v in self.voice_clients if v.channel.guild == v_c.guild][0]
                if voice.channel != v_c:
                    await voice.disconnect(force=True)
                    voice = await v_c.connect(timeout=5)

            if voice.is_playing():
                voice.stop()

            filename = '/tmp/soundfx-{}'.format(sound.id)

            if not os.path.isfile(filename):
                print('File not held. Caching into {}'.format(filename))

                with open(filename, 'wb') as f:
                    f.write(src)

            if volume == 100:
                voice.play(discord.FFmpegPCMAudio(filename))
            else:
                voice.play(discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(filename), volume / 100))

            sound.plays += 1

            session.commit()

    async def check_premium(self, member_id) -> bool:
        if member_id in config.fixed_donors:

            return True

        else:

            url = 'https://discordapp.com/api/v6/guilds/{}/members/{}'.format(config.patreon_server, member_id)

            head = {
                'Authorization': 'Bot {}'.format(config.bot_token),
                'Content-Type': 'application/json'
            }

            async with self.aiohttp_session.get(url, headers=head) as resp:

                if resp.status == 200:
                    member = await resp.json()
                    roles = [int(x) for x in member['roles']]

                else:
                    return False

            return config.donor_role in roles

    async def store(self, url):
        def b_store(u):
            sub = subprocess.Popen(('ffmpeg', '-i', u, '-loglevel', 'error', '-b:a', '28000', '-f', 'opus', 'pipe:1'),
                                   stdout=subprocess.PIPE)

            out = sub.stdout.read()
            if len(out) < 1:
                return b''

            else:
                return out

        m = await self.do_blocking(partial(b_store, url))
        return m

    @staticmethod
    def delete_sound(s):
        s.delete(synchronize_session='fetch')

    async def on_error(self, *args):
        session.rollback()
        raise

    # noinspection PyBroadException
    async def on_message(self, message):

        if isinstance(message.channel, discord.DMChannel) or message.author.bot or message.content is None:
            return

        if session.query(GuildData).get(message.guild.id) is None:
            s = GuildData(id=message.guild.id, name=message.guild.name, prefix='?', roles=['off'])
            session.add(s)
            session.commit()

        try:
            if message.channel.permissions_for(message.guild.me).send_messages and message.channel.permissions_for(
                    message.guild.me).embed_links:
                await self.get_cmd(message)
                session.commit()

        except:
            traceback.print_exc()

    async def get_cmd(self, message):

        guild_data: GuildData = session.query(GuildData).get(message.guild.id)
        prefix: str = guild_data.prefix

        command: typing.Optional[str] = None
        stripped: typing.Optional[str] = None

        if message.content[0:len(prefix)] == prefix:
            command = (message.content + ' ')[len(prefix):message.content.find(' ')]
            stripped = (message.content + ' ')[message.content.find(' '):].strip()

        elif self.user.id in map(lambda x: x.id, message.mentions) and len(message.content.split(' ')) > 1:
            command = message.content.split(' ')[1]
            stripped = (message.content + ' ').split(' ', 2)[-1].strip()

        if command in self.commands.keys():
            print(message.content)
            response: typing.Optional[str] = await self.commands[command].call(message.author, guild_data, message,
                                                                               stripped, guild_data)
            if response is not None:
                await message.channel.send(response)

    @staticmethod
    async def change_prefix(message, stripped, guild_data):
        if stripped:
            stripped += ' '
            new = stripped[:stripped.find(' ')]

            if len(new) > 5:
                await message.channel.send('Prefix must be shorter than 5 characters')

            else:
                guild_data.prefix = new
                await message.channel.send('Prefix changed to {}'.format(guild_data.prefix))

        else:
            await message.channel.send('Please use this command as `{}prefix <prefix>`'.format(guild_data.prefix))

    @staticmethod
    async def ping(message, _stripped, _server):
        t = message.created_at.timestamp()
        e = await message.channel.send('pong')
        delta = e.created_at.timestamp() - t

        await e.edit(content='Pong! {}ms round trip'.format(round(delta * 1000)))

    async def help(self, message, *_args):
        embed = discord.Embed(title='HELP', color=self.EMBED_COLOR,
                              description='Please visit https://soundfx.jellywx.com/help/'.format(self.user.name))
        await message.channel.send(embed=embed)

    async def info(self, message, _stripped, server):
        em = discord.Embed(title='INFO', color=self.EMBED_COLOR, description='''Default prefix: `?`

Reset prefix: `@{user} prefix ?`
Help: `{p}help`

Invite me: https://discordapp.com/oauth2/authorize?client_id=430384808200372245&scope=bot&permissions=36703232

**Welcome to SFX!**
Developer: <@203532103185465344>
Find me on https://discord.jellywx.com/ and on https://github.com/JellyWX :)

An online dashboard is available! Visit https://soundfx.jellywx.com/dashboard
There is a maximum sound limit per user. This can be removed by donating at https://patreon.com/jellywx

*If you have enquiries about new features, please send to the discord server*
*If you have enquiries about bot development for you or your server, please DM me*
        '''.format(user=self.user.name, p=server.prefix))

        await message.channel.send(embed=em)

    @staticmethod
    async def role(message, stripped, server):
        if 'everyone' in stripped:
            server.roles = []

            await message.channel.send('Role blacklisting disabled.')

        elif len(message.role_mentions) > 0:
            roles = [x.id for x in message.role_mentions]

            server.roles = roles

            await message.channel.send('Roles set. Please note members with `Manage Server` permissions will be'
                                       ' able to do sounds regardless of roles.')

        else:
            if len(server.roles) == 0:
                await message.channel.send(
                    'Please mention roles or `@everyone` to blacklist roles. Whitelisting is currently disabled.')
            else:
                await message.channel.send(
                    'Please mention roles or `@everyone` to blacklist roles. Current roles are <@&{}>'.format(
                        '>, <@&'.join([str(x) for x in server.roles])))

    # noinspection PyArgumentList
    async def wait_for_file(self, message, stripped, server):
        stripped = stripped.lower()

        current_sounds = session.query(Sound).filter(Sound.uploader_id == message.author.id)

        if current_sounds.count() >= config.max_sounds and not await self.check_premium(message.author.id):
            await message.channel.send(
                'Sorry, but the maximum is {} sounds per user. You can either use `{prefix}delete` to remove a '
                'sound or donate to get unlimited sounds at https://patreon.com/jellywx'.format(
                    config.max_sounds, prefix=server.prefix))

        elif stripped == '':
            await message.channel.send('Please provide a name for your sound in the command, e.g `?upload TERMINATION`')

        elif check_digits(stripped):
            await message.channel.send('Please use at least one non-numerical character in your sound\'s name'
                                       ' (this helps distinguish it from IDs)')

        elif len(stripped) > 20:
            await message.channel.send('Please choose a shorter name. You used {}/20 characters.'.format(len(stripped)))

        else:
            sound = session.query(Sound).filter(Sound.server_id == message.guild.id).filter(Sound.name == stripped)

            if sound.first() is not None:
                await message.channel.send('A sound in this server already exists under that name. Please either delete'
                                           ' that sound first, or choose a different name.')

            else:
                await message.channel.send(
                    'Saving as: `{}`. Send an audio file or send any other message to cancel.'.format(stripped))

                msg = await self.wait_for('message',
                                          check=lambda x: x.author == message.author and x.channel == message.channel)

                if len(msg.attachments) == 0:
                    await message.channel.send(
                        'Please attach an audio file following the `{}upload` command. Aborted.'.format(server.prefix))

                else:
                    out = await self.store(msg.attachments[0].url)

                    if len(out) < 1:
                        await message.channel.send('File not recognized as being a valid audio file.')

                    elif len(out) > 1000000:
                        await message.channel.send('Please only send audio files that are under 1MB compressed. '
                                                   'The bot uses Opus 28kbps compression when storing audio.')

                    else:
                        sound = Sound(src=out, server=server, uploader_id=message.author.id, name=stripped)

                        session.add(sound)

                        await message.channel.send(
                            'Sound saved as `{name}`! Use `{prefix}play {name}` to play the sound.'.format(
                                name=stripped, prefix=server.prefix))

    # noinspection PyUnresolvedReferences
    async def play(self, message, stripped, server):
        stripped = stripped.lower()

        if stripped == '':
            await message.channel.send(
                'You must specify the sound you wish to play. Use `{}list` to view all sounds.'.format(server.prefix))

        else:
            s: typing.Optional[Sound] = self.get_sound_by_string(stripped, message.guild.id, message.author.id)

            if s is None:

                await message.channel.send('Sound `{0}` could not be found. Use `{1}list` to view all sounds, '
                                           '`{1}search` to search for public sounds, or `{1}play ID:1234` to play '
                                           'a sound by ID'.format(stripped, server.prefix))

            else:
                if s.server.name is None:
                    g = self.get_guild(s.server_id)

                    if g is not None:
                        s.server.name = g.name

                name = s.server.name

                await message.channel.send('Playing sound **{name}** (ID `{id}`) from **{guild}**'.format(
                    name=s.name,
                    id=s.id,
                    guild=name,
                    pref=server.prefix
                )
                )

                await self.check_and_play(message.guild, message.channel, message.author, s, server)

    @staticmethod
    async def volume(message, stripped, server):
        stripped = stripped.replace('%', '')
        if check_digits(stripped):
            new_vol: int = int(stripped)
            if 0 < new_vol <= 250:
                server.volume = new_vol
                await message.channel.send('Volume changed')

            else:
                await message.channel.send(
                    'Provided volume is invalid. Volume must be greater than 0 and smaller than 250 (default: 100).')

        elif stripped == '':
            await message.channel.send(
                'Current server volume: {vol}%. Change the volume with ```{prefix}volume <new volume>```'.format(
                    vol=server.volume, prefix=server.prefix))

        else:
            await message.channel.send(
                "Couldn't interpret new volume. Please use as ```{prefix}volume <new volume>```".format(
                    prefix=server.prefix))

    async def stop(self, message, _stripped, _server):

        voice = [v for v in self.voice_clients if v.channel.guild == message.guild]
        if len(voice) == 0:
            await message.channel.send('Not connected to a VC!')
        else:
            await voice[0].disconnect(force=True)

    @staticmethod
    async def list(message, stripped, server):

        async def drain(queue):
            while not queue.empty():
                item = await queue.get()
                yield item

        strings = asyncio.Queue()

        if 'me' in stripped:
            a = session.query(Sound).filter(Sound.uploader_id == message.author.id)
        else:
            a = server.sounds

        for s in a:
            string = '**{}**'.format(s.name, s)
            if s.public:
                string += ' (\U0001F513)'
            else:
                string += ' (\U0001F510)'

            await strings.put(string)

        if 'me' in stripped:
            opener = 'All your sounds: '
        else:
            opener = 'All sounds on this server: '

        current_buffer = opener

        async for s in drain(strings):
            if len(current_buffer) + len(s) >= 2000:
                await message.channel.send(current_buffer.strip(', '))
                current_buffer = s
            else:
                current_buffer += '{}, '.format(s)

        if len(current_buffer) > 0:
            await message.channel.send(current_buffer.strip(', '))

    @staticmethod
    def search_by_name(name, uploader_id, guild_id):
        name = name.lower()

        q = session.query(Sound) \
            .filter(Sound.name == name) \
            .filter(
            (Sound.uploader_id == uploader_id) | (Sound.server_id == guild_id)
        ) \
            .order_by(Sound.uploader_id != uploader_id) \
            .first()

        return q

    async def delete(self, message, stripped, server):
        q = self.search_by_name(stripped, message.author.id, message.guild.id)

        if q is None:
            await message.channel.send(
                "Couldn't find sound by name {}. Use `{}list` to view all sounds.".format(stripped, server.prefix))

        else:
            self.delete_sound(session.query(Sound).filter(Sound.id == q.id))
            await message.channel.send('Deleted `{}`'.format(stripped))

    async def public(self, message, stripped, server):
        s = self.search_by_name(stripped, message.author.id, message.guild.id)

        if s is not None:
            s.public = not s.public
            await message.channel.send('Sound `{}` has been set to {}.'.format(
                stripped, 'public \U0001F513' if s.public else 'private \U0001F510'))

        else:
            await message.channel.send(
                "Couldn't find sound by name {}. Use `{}list` to view all sounds.".format(stripped, server.prefix))

    @staticmethod
    async def search(message, stripped, _guild_data):

        embed = discord.Embed(title='Public sounds matching filter:')

        length = 0

        if 'popular' in message.content.split(' ')[0]:
            for sound in session.query(Sound).filter(Sound.public).order_by(Sound.plays.desc()).limit(25):
                if length < 2000:
                    content = 'ID: {}\nPlays: {}'.format(sound.id, sound.plays)

                    embed.add_field(name=sound.name, value=content, inline=True)

                    length += len(content) + len(sound.name)

                else:
                    break

        elif 'random' in message.content.split(' ')[0]:
            for sound in session.query(Sound).filter(Sound.public).order_by(func.rand()).limit(25):
                if length < 2000:
                    content = 'ID: {}\nPlays: {}'.format(sound.id, sound.plays)

                    embed.add_field(name=sound.name, value=content, inline=True)

                    length += len(content) + len(sound.name)

                else:
                    break

        else:
            for sound in session.query(Sound).filter(Sound.public).filter(
                    Sound.name.ilike('%{}%'.format(stripped))).limit(25):

                if length < 2000:
                    content = 'ID: {}\nPlays: {}'.format(sound.id, sound.plays)

                    embed.add_field(name=sound.name, value=content, inline=True)

                    length += len(content) + len(sound.name)

                else:
                    embed.set_footer(text='More results were found, but removed due to size restrictions')
                    break

        await message.channel.send(embed=embed)

    # noinspection PyBroadException
    async def cleanup(self):
        await self.wait_until_ready()

        while not client.is_closed():

            try:
                [await vc.disconnect(force=True) for vc in self.voice_clients if not vc.is_playing()]

            except:
                pass

            await asyncio.sleep(600)


client = BotClient(max_messages=100, guild_subscriptions=False, fetch_offline_members=False)

client.loop.create_task(client.cleanup())

client.run(config.bot_token)
