from tinyconf.fields import Field, IntegerField, ListField
from tinyconf.deserializers import IniDeserializer
from tinyconf.section import Section


class Config(IniDeserializer):
    bot_token = Field('bot', strict=True)
    dbl_token = Field('discordbots', strict=False)

    patreon_server = IntegerField()
    donor_role = IntegerField()
    fixed_donors = ListField(map=lambda x: int(x.strip()), default=[])

    max_sounds = IntegerField()

    user = Field(strict=True)
    passwd = Field(strict=False)
    host = Field(strict=False, default='localhost')
    database = Field(strict=False, default='soundfx')

    TOKENS = Section(bot_token, dbl_token)
    MYSQL = Section(user, passwd, host, database)
    DEFAULT = Section(patreon_server, donor_role, fixed_donors, max_sounds)


config = Config(filename='config.ini')
