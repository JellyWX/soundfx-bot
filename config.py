from tinyconf.fields import Field, IntegerField, ListField
from tinyconf.deserializers import IniDeserializer

class Config(IniDeserializer):
    bot_token = Field('bot', strict=True)
    dbl_token = Field('discordbots', strict=False)

    patreon_server = IntegerField()
    donor_role = IntegerField()
    fixed_donors = ListField(map=lambda x: int(x.strip()), default=[])

    max_sounds = IntegerField()
    max_sound_store = IntegerField()