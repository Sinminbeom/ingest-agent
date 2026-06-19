from python_library.singleton.singleton import Singleton

from utils.time_string_fit import TimeStringFit, E_TIMEFORMAT


class ProtocolUtils(Singleton):
    def __init__(self):
        super().__init__()
        self.sequence_id = {}

    def get_sequence_id_now(self):
        field_key = TimeStringFit().get(E_TIMEFORMAT.YYYYMMDDHH24MISS)

        if field_key in self.sequence_id:
            self.sequence_id[field_key] += 1
        else:
            self.sequence_id[field_key] = 0

        seq = int(self.sequence_id[field_key])
        return field_key + "_" + f"{seq:08}"
