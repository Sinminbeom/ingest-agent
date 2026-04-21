from datetime import datetime
from dateutil.relativedelta import relativedelta

from oncx_core.define.enum import IENUM


class E_TIMEFORMAT(IENUM):
    YYYYMMDDHH24MISS = "yyyyMMddHHmmss"
    YYYYMMDDHH24MI = "yyyyMMddHHmm"
    YYYYMMDDHH24 = "yyyyMMddHH"
    YYYYMMDD = "yyyyMMdd"
    YYYYMM = "yyyyMM"
    YYYY = "yyyy"

    MM = "MM"
    DD = "dd"
    HH24 = "HH"
    MI = "mm"
    SS = "ss"


class E_CALENDAR_TYPE(IENUM):
    YEAR = 1
    MONTH = 2
    DAY = 3
    HOUR = 4
    MIN = 5
    SEC = 6


class TimeStringInterval:
    def __init__(self, calendar_type: str, interval: int):
        self._calendar_type: str = calendar_type
        self._interval: int = interval

    def get_interVal(self) -> int:
        return self._interval

    def get_calendar_type(self) -> str:
        return self._calendar_type


class TimeStringFit:
    def __init__(self):
        self.set_current()
        pass

    def set(self, time_string):
        if len(time_string) < len(E_TIMEFORMAT.YYYY) or len(time_string) > len(
            E_TIMEFORMAT.YYYYMMDDHH24MISS
        ):
            raise Exception(
                "TimeStringFit : SetTimeString not enaught  to time string length "
            )

        self.mvalue = self._fillZero(time_string)

    def _fillZero(self, _time_string):
        # E_TIMEFORMAT.get( E_TIMEFORMAT.YYYYMMDDHH24MISS )
        time_string = self._fillYYYMMDD(_time_string)

        rlen = len(E_TIMEFORMAT.YYYYMMDDHH24MISS) - len(time_string)

        if rlen == 0:
            return time_string

        time_string += "0" * rlen

        return time_string

    def _fillYYYMMDD(self, time_string):
        if len(time_string) < len(E_TIMEFORMAT.YYYY):
            raise Exception

        if len(time_string) < len(E_TIMEFORMAT.YYYYMM):
            return time_string[: len(E_TIMEFORMAT.YYYY)] + "0101"

        if len(time_string) < len(E_TIMEFORMAT.YYYYMMDD):
            return time_string[: len(E_TIMEFORMAT.YYYYMM)] + "01"
        return time_string

    def set_current(self):
        now = datetime.now()
        self.set(now.strftime("%Y%m%d%H%M%S"))

    def get(self, time_format: str = E_TIMEFORMAT.YYYYMMDDHH24MISS):
        begin = 0
        last = 0
        if time_format == E_TIMEFORMAT.MM:
            begin = len(E_TIMEFORMAT.YYYY)
            last = len(E_TIMEFORMAT.YYYYMM)
        elif time_format == E_TIMEFORMAT.DD:
            begin = len(E_TIMEFORMAT.YYYYMM)
            last = len(E_TIMEFORMAT.YYYYMMDD)
        elif time_format == E_TIMEFORMAT.HH24:
            begin = len(E_TIMEFORMAT.YYYYMMDD)
            last = len(E_TIMEFORMAT.YYYYMMDDHH24)
        elif time_format == E_TIMEFORMAT.MI:
            begin = len(E_TIMEFORMAT.YYYYMMDDHH24)
            last = len(E_TIMEFORMAT.YYYYMMDDHH24MI)
        elif time_format == E_TIMEFORMAT.SS:
            begin = len(E_TIMEFORMAT.YYYYMMDDHH24MI)
            last = len(E_TIMEFORMAT.YYYYMMDDHH24MISS)
        else:
            last = len(time_format)
        return self.mvalue[begin:last]

    def _getRelativedelta(self, calendar_type, calc_vaule):
        if calendar_type == E_CALENDAR_TYPE.YEAR:
            return relativedelta(years=calc_vaule)
        elif calendar_type == E_CALENDAR_TYPE.MONTH:
            return relativedelta(months=calc_vaule)
        elif calendar_type == E_CALENDAR_TYPE.DAY:
            return relativedelta(days=calc_vaule)
        elif calendar_type == E_CALENDAR_TYPE.HOUR:
            return relativedelta(hours=calc_vaule)
        elif calendar_type == E_CALENDAR_TYPE.MIN:
            return relativedelta(minutes=calc_vaule)
        elif calendar_type == E_CALENDAR_TYPE.SEC:
            return relativedelta(seconds=calc_vaule)

        raise Exception("_getRelativedelta Not Found  calendar_type ")

    def calc_datetime(self, calendar_type, calc_vaule):
        time = datetime.strptime(self.get(), "%Y%m%d%H%M%S")

        time_calc = (time + self._getRelativedelta(calendar_type, calc_vaule)).strftime(
            "%Y%m%d%H%M%S"
        )

        ntime = TimeStringFit()
        ntime.set(time_calc)
        return ntime

    def next(self, calendar_type, calc_vaule):
        time = datetime.strptime(self.get(), "%Y%m%d%H%M%S")
        time_calc = (time + self._getRelativedelta(calendar_type, calc_vaule)).strftime(
            "%Y%m%d%H%M%S"
        )
        self.set(time_calc)

    def equal(self, time_string_fit):
        if self.get() == time_string_fit.get():
            return True

        return False

    @staticmethod
    def diff_sec(time_string1, time_string2):
        startTime = TimeStringFit()
        startTime.set(time_string1)

        targetTime = TimeStringFit()
        targetTime.set(time_string2)

        time1 = datetime.strptime(startTime.get(), "%Y%m%d%H%M%S")
        time2 = datetime.strptime(targetTime.get(), "%Y%m%d%H%M%S")
        diff = time2 - time1
        return int(diff.total_seconds())

    @staticmethod
    def diff_min(time_string1, time_string2):
        return TimeStringFit.diff_sec(time_string1, time_string2) / 60

    ##    Useage ..
    ##    TimeStringFit().CoRoution( "202306231010" , "20230623101110" ,
    ##                             TimeStringInterval( E_CALENDAR_TYPE.SEC , 4 ) ,
    ##                             lambda time_string_fit :  print( time_string_fit.get() )

    @staticmethod
    def coroutine(
        start_time, target_time, time_string_interval, action1, comparator="<"
    ):
        import operator

        ops = {
            "<": operator.lt,
            "<=": operator.le,
            "==": operator.eq,
            "!=": operator.ne,
            ">": operator.gt,
            ">=": operator.ge,
        }

        if comparator not in ops:
            raise ValueError(f"Invalid comparator: {comparator}")

        st = TimeStringFit()
        st.set(start_time)

        tg = TimeStringFit()
        tg.set(target_time)

        while ops[comparator](st.get(), tg.get()):
            action1(st)
            st.next(
                time_string_interval.GetCalendarType(),
                time_string_interval.GetInterVal(),
            )

    # TimeStringFit().Coroutine("202310", "202312",
    #                            TimeStringInterval(E_CALENDAR_TYPE.MONTH, 1),
    #                            lambda time_string_fit: print(time_string_fit.get()),
    #                            "<="
    #                            )
    #
    # TimeStringFit().Coroutine("2023", "2025",
    #                            TimeStringInterval(E_CALENDAR_TYPE.YEAR, 1),
    #                            lambda time_string_fit: print(time_string_fit.get()),
    #                            "<="
    #                            )

    #
    # # print(  E_TIMEFORMAT.get( E_TIMEFORMAT.YYYYMMDDHH24MISS ))
    #
    # print( TimeStringFit.DiffSec("202306231335" ,"20230623133710" ) )
    # print( TimeStringFit.DiffMin("202306231335" ,"20230623133710" ) )
    #
    # print(TimeStringFit.DiffSec("202306231339", "20230623133710"))
    #
    #
    # cm = TimeStringFit()
    # print(cm.get())
    #
    # print("===================================")
    # print(cm.get(E_TIMEFORMAT.YYYYMMDDHH24MISS))
    # print(cm.get(E_TIMEFORMAT.YYYYMMDDHH24MI))
    # print(cm.get(E_TIMEFORMAT.YYYYMMDDHH24))
    # print(cm.get(E_TIMEFORMAT.YYYYMMDD))
    # print(cm.get(E_TIMEFORMAT.YYYYMM))
    # print(cm.get(E_TIMEFORMAT.YYYY))
    #
    # print("----------------------------------------")
    #
    # print(cm.get(E_TIMEFORMAT.MM))
    # print(cm.get(E_TIMEFORMAT.DD))
    # print(cm.get(E_TIMEFORMAT.HH24))
    # print(cm.get(E_TIMEFORMAT.MI))
    # print(cm.get(E_TIMEFORMAT.SS))
    #
    # print("****************************************")
    #
    # cm.set("20230405011011")
    #
    # print(cm.get())
    #
    #
    # ncm = cm.CalcDateTime(  E_CALENDAR_TYPE.MIN , 10 )
    #
    # print(ncm.get() )
    #
    # print("===================")
    #
    # TimeStringFit().Coroutine( "202306231010" , "20230623101110" ,
    #                             cTimeStringInterVal( E_CALENDAR_TYPE.SEC , 4 ) ,
    #                             lambda time_string_fit :  print( time_string_fit.get() )
    #                             )
    #
    # print("====##################################################################################===============")
    #
    # TimeStringFit().Coroutine( "202306231010" , "20230623101110" ,
    #                             cTimeStringInterVal( E_CALENDAR_TYPE.SEC , 1 ) ,
    #                             lambda time_string_fit :  print( time_string_fit.get() )
    #                             )
    #
    # print("====ww################################################wwww##################################===============")
    #
    # TimeStringFit().Coroutine( "202306231010" , "20230623101110" ,
    #                             cTimeStringInterVal( E_CALENDAR_TYPE.SEC , 1 ) ,
    #                             lambda time_string_fit :  print( time_string_fit.get() ) ,
    #                             "<="
    #                             )
