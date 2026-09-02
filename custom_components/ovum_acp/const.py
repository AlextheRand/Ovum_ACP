"""Constants and register definitions for Ovum MIRA Wärmepumpe."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum, auto

DOMAIN = "ovum_acp"
MANUFACTURER = "Ovum"
MODEL = "MIRA"

# Modbus defaults
DEFAULT_HOST = "192.168.178.82"
DEFAULT_PORT = 502
DEFAULT_SCAN_INTERVAL = 30

# Login constants (FC16 to addr 101 on each slave)
LOGIN_ADDRESS = 101
LOGIN_INTERVAL_SECONDS = 25 * 60  # Re-login every 25 min
# Default login code "1" = disabled (user must set it to 1 at display, or enter their code)
DEFAULT_LOGIN_CODE = 1  # 0x00000001 — login disabled at display

# HSM slave (always present)
SLAVE_HSM = 110
# WPM slaves: 111 = WPM1, 112 = WPM2, ... 118 = WPM8
SLAVE_WPM_BASE = 111


class Level(IntEnum):
    L1 = 1  # Start Values (free)
    L2 = 2  # Plus Values (paid)
    L3 = 3  # BMS Values (paid)


class DataType(IntEnum):
    INT16 = auto()    # 1 register, signed 16-bit
    UINT16 = auto()   # 1 register, unsigned 16-bit
    INT32 = auto()    # 2 registers, signed 32-bit big-endian
    FLOAT32 = auto()  # 2 registers, IEEE 754 big-endian
    BOOL = auto()     # 1 register, 0/1


class FC(IntEnum):
    """Modbus function code for reads."""
    FC3 = 3   # Read Holding Registers — Level 1/2 (55000-56999) and Level 3 config (40000-46999)
    FC4 = 4   # Read Input Registers — Level 3 diagnostics (30000-35999)


@dataclass(frozen=True)
class RegisterDef:
    """Definition of a single Modbus register or register group."""

    name: str
    """Internal key used as coordinator data dict key."""

    address: int
    """0-based Modbus address."""

    slave: int
    """Modbus slave ID (110=HSM, 111=WPM1, ...)."""

    data_type: DataType
    fc: FC = FC.FC3
    writable: bool = False
    level: Level = Level.L1
    unit: str = ""
    min_value: float | None = None
    max_value: float | None = None
    description: str = ""
    scale: float = 1.0

    # Config flags — which integration configs expose this register
    requires_ww_internal: bool = False  # Only with Frischwasserstation (internal WW)
    requires_cooling: bool = False      # Only when cooling is configured
    hk_index: int | None = None        # Which HK this belongs to (1-4), None = global

    @property
    def count(self) -> int:
        """Number of Modbus registers consumed."""
        if self.data_type in (DataType.FLOAT32, DataType.INT32):
            return 2
        return 1


# ---------------------------------------------------------------------------
# Helper: generate per-HK register sets
# ---------------------------------------------------------------------------

def _hk_registers_l1(n: int) -> list[RegisterDef]:
    """Level 1 core HK block: 56050 + (n-1)*10, 10 registers."""
    base = 56050 + (n - 1) * 10
    level = Level.L1 if n <= 2 else Level.L2
    return [
        RegisterDef(f"hk{n}_type",        base + 0,  SLAVE_HSM, DataType.INT16,   level=level, hk_index=n,
                    description="Heizkreistyp (0=AUS, 1=FUSSBODEN, 2=HEIZKÖRPER, 3=POOL)"),
        RegisterDef(f"hk{n}_pv_plus",     base + 1,  SLAVE_HSM, DataType.INT16,   level=level, hk_index=n,
                    unit="K", description="Kelvin-Offset auf Solltemp bei PV-Status Erhöhen"),
        RegisterDef(f"hk{n}_pv_minus",    base + 2,  SLAVE_HSM, DataType.INT16,   level=level, hk_index=n,
                    unit="K", description="Kelvin-Offset auf Solltemp bei PV-Status Reduzieren"),
        RegisterDef(f"hk{n}_desiredtemp", base + 3,  SLAVE_HSM, DataType.FLOAT32, level=level, hk_index=n,
                    writable=(n <= 2), unit="°C", min_value=10.0, max_value=75.0,
                    description="Heizkreis Solltemperatur (RW für HK1/2, RO für HK3/4)"),
        RegisterDef(f"hk{n}_actualvalue", base + 5,  SLAVE_HSM, DataType.FLOAT32, level=level, hk_index=n,
                    unit="°C", description="Heizkreis Ist-Vorlauftemperatur"),
        RegisterDef(f"hk{n}_mode",        base + 7,  SLAVE_HSM, DataType.INT16,   level=level, hk_index=n,
                    writable=True, description="Betriebsmodus (0=AUS, 1=AUTOMATIK, 2=WINTER, 3=SOMMER)"),
        RegisterDef(f"hk{n}_raumsoll_hz", base + 8,  SLAVE_HSM, DataType.FLOAT32, level=level, hk_index=n,
                    writable=True, unit="°C", min_value=10.0, max_value=30.0,
                    description="Raumsolltemperatur Heizbetrieb"),
    ]


def _hk_registers_l2_ext(n: int) -> list[RegisterDef]:
    """Level 2 extended HK block: 56150 + (n-1)*25, 12 registers."""
    base = 56150 + (n - 1) * 25
    return [
        RegisterDef(f"hk{n}_raumsoll_kue",   base + 0,  SLAVE_HSM, DataType.FLOAT32, level=Level.L2,
                    writable=True, requires_cooling=True, hk_index=n,
                    unit="°C", min_value=16.0, max_value=30.0,
                    description="Raumsolltemperatur Kühlbetrieb"),
        RegisterDef(f"hk{n}_actualroomtemp", base + 2,  SLAVE_HSM, DataType.FLOAT32, level=Level.L2,
                    hk_index=n, unit="°C", description="Aktuell gemessene Raumtemperatur"),
        RegisterDef(f"hk{n}_urlaub",         base + 4,  SLAVE_HSM, DataType.INT16,   level=Level.L2,
                    writable=True, hk_index=n, description="Urlaubsmodus (0=AUS, 1=EIN)"),
        RegisterDef(f"hk{n}_tvl_urlaub_hz",  base + 5,  SLAVE_HSM, DataType.INT16,   level=Level.L2,
                    writable=True, hk_index=n, unit="°C",
                    description="Vorlaufsollwert Urlaub Heizbetrieb"),
        RegisterDef(f"hk{n}_tvl_urlaub_kue", base + 6,  SLAVE_HSM, DataType.INT16,   level=Level.L2,
                    writable=True, requires_cooling=True, hk_index=n, unit="°C",
                    description="Vorlaufsollwert Urlaub Kühlbetrieb"),
        RegisterDef(f"hk{n}_fix_mode",       base + 7,  SLAVE_HSM, DataType.INT16,   level=Level.L2,
                    writable=True, hk_index=n,
                    description="Sollwertbildung (0=AUTO, 1=FIX_HEIZEN, 2=FIX_KUEHLEN)"),
        RegisterDef(f"hk{n}_fixwert_hz",     base + 8,  SLAVE_HSM, DataType.INT16,   level=Level.L2,
                    writable=True, hk_index=n, unit="°C", min_value=0.0, max_value=100.0,
                    description="Fixwert Heizen (nur im FIX_HEIZEN-Mode aktiv)"),
        RegisterDef(f"hk{n}_fixwert_kue",    base + 9,  SLAVE_HSM, DataType.INT16,   level=Level.L2,
                    writable=True, requires_cooling=True, hk_index=n, unit="°C",
                    min_value=0.0, max_value=100.0,
                    description="Fixwert Kühlen (nur im FIX_KUEHLEN-Mode aktiv)"),
        RegisterDef(f"hk{n}_at_heizgrenze",  base + 10, SLAVE_HSM, DataType.FLOAT32, level=Level.L2,
                    writable=True, hk_index=n, unit="°C", min_value=5.0, max_value=25.0,
                    description="Außentemperatur-Heizgrenze: ab hier kein Heizbetrieb"),
    ]


def _wpm_registers_l1(wpm_idx: int) -> list[RegisterDef]:
    """Level 1 WPM registers (same set for each WPM, slave = 111 + wpm_idx - 1)."""
    slave = SLAVE_WPM_BASE + wpm_idx - 1
    return [
        RegisterDef(f"wpm{wpm_idx}_aufnahmeleistung",  56021, slave, DataType.FLOAT32, level=Level.L1,
                    unit="W", scale=1000.0, description="Aufnahmeleistung WP"),
        RegisterDef(f"wpm{wpm_idx}_waermeleistung",    56023, slave, DataType.FLOAT32, level=Level.L1,
                    unit="W", scale=1000.0, description="Wärmeleistung WP (keine geeichte Messung)"),
        RegisterDef(f"wpm{wpm_idx}_status",            56025, slave, DataType.INT16,   level=Level.L1,
                    description="WP-Statuscode"),
        RegisterDef(f"wpm{wpm_idx}_eintrittstemperatur", 56026, slave, DataType.FLOAT32, level=Level.L1,
                    unit="°C", description="Eintrittstemperatur WP"),
        RegisterDef(f"wpm{wpm_idx}_austrittstemperatur", 56028, slave, DataType.FLOAT32, level=Level.L1,
                    unit="°C", description="Austrittstemperatur WP"),
        RegisterDef(f"wpm{wpm_idx}_betriebsstunden",  56030, slave, DataType.INT32,   level=Level.L1,
                    unit="h", scale=1/60, description="Betriebsstunden Verdichter (Register in Minuten)"),
    ]


def _wpm_registers_l3(wpm_idx: int) -> list[RegisterDef]:
    """Level 3 (BMS) WPM registers — FC4 Input Registers."""
    slave = SLAVE_WPM_BASE + wpm_idx - 1
    return [
        RegisterDef(f"wpm{wpm_idx}_hgt",         30004, slave, DataType.FLOAT32, FC.FC4, level=Level.L3,
                    unit="°C", description="Heißgastemperatur"),
        RegisterDef(f"wpm{wpm_idx}_sgt",         30006, slave, DataType.FLOAT32, FC.FC4, level=Level.L3,
                    unit="°C", description="Sauggastemperatur"),
        RegisterDef(f"wpm{wpm_idx}_koet",        30010, slave, DataType.FLOAT32, FC.FC4, level=Level.L3,
                    unit="°C", description="Kondensatoreintrittstemperatur"),
        RegisterDef(f"wpm{wpm_idx}_koat",        30012, slave, DataType.FLOAT32, FC.FC4, level=Level.L3,
                    unit="°C", description="Kondensatoraustrittstemperatur"),
        RegisterDef(f"wpm{wpm_idx}_ko_flow",     30030, slave, DataType.FLOAT32, FC.FC4, level=Level.L3,
                    unit="l/min", description="Volumenstrom durch WP"),
        RegisterDef(f"wpm{wpm_idx}_eev_pos",     30064, slave, DataType.INT16,   FC.FC4, level=Level.L3,
                    unit="%", description="EEV-Ventilposition"),
        RegisterDef(f"wpm{wpm_idx}_co_pump",     30066, slave, DataType.INT16,   FC.FC4, level=Level.L3,
                    unit="%", description="Kondensatorpumpe Drehzahl"),
        RegisterDef(f"wpm{wpm_idx}_rps",         30069, slave, DataType.INT16,   FC.FC4, level=Level.L3,
                    unit="rps", description="Verdichterdrehzahl"),
        RegisterDef(f"wpm{wpm_idx}_cop",         30088, slave, DataType.FLOAT32, FC.FC4, level=Level.L3,
                    unit="", description="Aktueller COP"),
        RegisterDef(f"wpm{wpm_idx}_wpm_status",  30099, slave, DataType.INT16,   FC.FC4, level=Level.L3,
                    description="Detaillierter WP-Status (0=Störung, 5=Bereit, 7=WW, 8=HZ, 9=Kühlen, 10=Abtauen)"),
        RegisterDef(f"wpm{wpm_idx}_compressor_starts", 30126, slave, DataType.INT32, FC.FC4, level=Level.L3,
                    description="Schaltungen Verdichter"),
        RegisterDef(f"wpm{wpm_idx}_error_status",30450, slave, DataType.INT16,   FC.FC4, level=Level.L3,
                    description="Fehlerstatus Bitfeld (BIT1=Ereignis, BIT2=Warnung, BIT3=Störung, BIT4=Störung+Sperre)"),
        RegisterDef(f"wpm{wpm_idx}_errorcode_1", 30460, slave, DataType.INT16,   FC.FC4, level=Level.L3,
                    description="Fehlercode letzter Störung 1"),
        RegisterDef(f"wpm{wpm_idx}_errorcode_2", 30461, slave, DataType.INT16,   FC.FC4, level=Level.L3,
                    description="Fehlercode letzter Störung 2"),
        RegisterDef(f"wpm{wpm_idx}_warningcode_1", 30470, slave, DataType.INT16, FC.FC4, level=Level.L3,
                    description="Warningcode 1"),
        RegisterDef(f"wpm{wpm_idx}_warningcode_2", 30471, slave, DataType.INT16, FC.FC4, level=Level.L3,
                    description="Warningcode 2"),
    ]


# ---------------------------------------------------------------------------
# Master register list (HSM static registers)
# ---------------------------------------------------------------------------

HSM_REGISTERS: list[RegisterDef] = [
    # --- WW Registers (Level 1) ---
    RegisterDef("ww_switch_on",     55000, SLAVE_HSM, DataType.INT16,   writable=True,
                description="WW-Hauptschalter (0=AUS, 1=EIN)"),
    RegisterDef("ww_soll",          55001, SLAVE_HSM, DataType.INT16,   writable=True,
                unit="°C", min_value=10.0, max_value=62.0,
                description="WW-Speichersollwert (aktiv geschriebener Sollwert)"),
    RegisterDef("ww_soll_pv",       55002, SLAVE_HSM, DataType.INT16,   writable=True,
                unit="°C", min_value=10.0, max_value=67.0,
                description="WW-Sollwert bei PV-Status Erhöhen"),
    RegisterDef("ww_desiredtemp",   55004, SLAVE_HSM, DataType.FLOAT32,
                unit="°C", description="WW-Soll aktiv (read-back, float)"),
    RegisterDef("ww_temp_oben",     55007, SLAVE_HSM, DataType.FLOAT32,
                unit="°C", description="WW-Speichertemperatur Oben"),
    RegisterDef("ww_temp_unten",    55009, SLAVE_HSM, DataType.FLOAT32,
                unit="°C", description="WW-Speichertemperatur Unten"),

    # --- WW Level 2 ---
    RegisterDef("ww_anfstatus",     55012, SLAVE_HSM, DataType.INT16,   level=Level.L2,
                description="WW-Anforderungsstatus (0=Keine, 1=PLUS, 2=PV, 3=Legionellen, 4=Soll, 5=Turbo, 6=Frost)"),
    RegisterDef("fws_soll",         55014, SLAVE_HSM, DataType.INT16,   level=Level.L2,
                writable=True, requires_ww_internal=True, unit="°C", min_value=10.0, max_value=65.0,
                description="Frischwassersystem Sollwert (nur bei interner WW)"),
    RegisterDef("ww_fwsstsstatus",  55015, SLAVE_HSM, DataType.INT16,   level=Level.L2,
                requires_ww_internal=True,
                description="Frischwasserstation Status (0=Kein Fluss, 1=Standby, 2=Zapfung)"),
    RegisterDef("ww_zirkpump",      55016, SLAVE_HSM, DataType.BOOL,    level=Level.L2,
                description="Zirkulationspumpe Status"),
    RegisterDef("ww_zirkt",         55017, SLAVE_HSM, DataType.FLOAT32, level=Level.L2,
                unit="°C", description="Zirkulationstemperatur"),
    RegisterDef("ww_urlaub",        55019, SLAVE_HSM, DataType.INT16,   level=Level.L2,
                description="WW-Urlaubsmodus"),

    # --- Puffer (Level 1) ---
    RegisterDef("hpuf_soll_pv",     55021, SLAVE_HSM, DataType.INT16,   writable=True,
                unit="°C", min_value=0.0, max_value=70.0,
                description="Pufferspeicher Sollwert bei PV-Status Erhöhen"),
    RegisterDef("hpuf_status",      55022, SLAVE_HSM, DataType.INT16,   level=Level.L2,
                description="Puffer Status (1=Heizen, 2=Kühlen)"),
    RegisterDef("hpuf_solltemp",    55023, SLAVE_HSM, DataType.FLOAT32,
                unit="°C", description="Pufferspeicher Sollwert aktiv"),
    RegisterDef("puffer_temp_oben", 55026, SLAVE_HSM, DataType.FLOAT32,
                unit="°C", description="Heizungspuffer Istwert Oben (T3)"),
    RegisterDef("puffer_temp_unten",55028, SLAVE_HSM, DataType.FLOAT32,
                unit="°C", description="Heizungspuffer Istwert Unten (T4)"),
    RegisterDef("hpuf_ladestatus",  55030, SLAVE_HSM, DataType.INT16,   level=Level.L2,
                description="Puffer Ladestatus (0=unter Frost, 1=unter Einschaltpunkt, 2=unter Soll, 3=über Soll, 4=über Soll+Hys, 5=kein Puffer)"),

    # --- EMS/PV Control (Level 1, RW) ---
    RegisterDef("ems_pvstatus",     55070, SLAVE_HSM, DataType.INT16,   writable=True,
                description="PV-Status Vorgabe (0=Neutral, 1=Erhöhen, 2=Reduzieren)"),
    RegisterDef("ems_bat_soc",      55071, SLAVE_HSM, DataType.INT16,   writable=True,
                unit="%", min_value=0.0, max_value=100.0,
                description="Batterie-SOC Vorgabe an MIRA"),
    RegisterDef("ems_grid_power",   55072, SLAVE_HSM, DataType.INT16,   writable=True,
                unit="W", description="Netzbezug/-einspeisung Vorgabe (positiv=Bezug)"),
    RegisterDef("ems_wr_power",     55073, SLAVE_HSM, DataType.INT16,   writable=True,
                unit="W", description="WR-Leistung Vorgabe"),
    RegisterDef("ems_target_power", 55074, SLAVE_HSM, DataType.INT16,   writable=True,
                unit="W", description="Zielleistung Vorgabe an MIRA"),

    # --- EMS PV Enable Status (Level 2, RO) ---
    RegisterDef("hsm_pvenable_wpww",  55079, SLAVE_HSM, DataType.INT16, level=Level.L2,
                description="PV-Freigabestatus WP für WW"),
    RegisterDef("hsm_pvenable_wphz",  55081, SLAVE_HSM, DataType.INT16, level=Level.L2,
                description="PV-Freigabestatus WP für Heizung"),
    RegisterDef("hsm_pvenable_st2ww", 55083, SLAVE_HSM, DataType.INT16, level=Level.L2,
                description="PV-Freigabestatus Zusatzheizung WW"),
    RegisterDef("hsm_pvenable_st2hz", 55085, SLAVE_HSM, DataType.INT16, level=Level.L2,
                description="PV-Freigabestatus Zusatzheizung Heizung"),

    # --- Cooling (Level 2) ---
    RegisterDef("sys_kue_puffer",    55040, SLAVE_HSM, DataType.INT16,  level=Level.L2,
                requires_cooling=True, description="Separater Kühlpuffer installiert (0=NEIN, 1=JA)"),
    RegisterDef("kpuf_puut",         55041, SLAVE_HSM, DataType.FLOAT32, level=Level.L2,
                requires_cooling=True, unit="°C", description="Kühlpuffer Istwert"),
    RegisterDef("kpuf_solltemp",     55043, SLAVE_HSM, DataType.FLOAT32, level=Level.L2,
                requires_cooling=True, unit="°C", description="Kühlpuffer Sollwert aktiv"),
    RegisterDef("kpuf_ladestatus",   55045, SLAVE_HSM, DataType.INT16,  level=Level.L2,
                requires_cooling=True,
                description="Kühlpuffer Ladestatus (0=über Soll+Hys, 3=unter Soll, 5=kein Kühlpuffer)"),

    # --- Cascade / Bivalenz (Level 2) ---
    RegisterDef("biv_kaskwwanf",     55058, SLAVE_HSM, DataType.BOOL,   level=Level.L2,
                description="Warmwasseranforderung an Kaskade"),
    RegisterDef("biv_kaskhzanf",     55059, SLAVE_HSM, DataType.BOOL,   level=Level.L2,
                description="Heizungsanforderung an Kaskade"),
    RegisterDef("biv_kaskkueanf",    55060, SLAVE_HSM, DataType.BOOL,   level=Level.L2,
                requires_cooling=True, description="Kühlanforderung an Kaskade"),

    # --- System (Level 2) ---
    RegisterDef("sys_snrkey",        56010, SLAVE_HSM, DataType.INT16,  level=Level.L2,
                description="Seriennummer Key"),

    # --- Außentemperatur (Level 1) ---
    RegisterDef("aussentemperatur",  56048, SLAVE_HSM, DataType.FLOAT32,
                unit="°C", description="Außentemperatur"),

    # --- Level 3: HSM BMS Input Registers (FC4) ---
    RegisterDef("hsm_lk_a_mode",    30510, SLAVE_HSM, DataType.INT16, FC.FC4, level=Level.L3,
                description="Ladekreis A Betriebsmodus (0=AUS, 1=WW, 2=HZ, 3=KÜ)"),
    RegisterDef("hsm_lk_b_mode",    30511, SLAVE_HSM, DataType.INT16, FC.FC4, level=Level.L3,
                description="Ladekreis B Betriebsmodus"),
    RegisterDef("hsm_lk_c_mode",    30512, SLAVE_HSM, DataType.INT16, FC.FC4, level=Level.L3,
                description="Ladekreis C Betriebsmodus"),
    RegisterDef("hsm_lk_d_mode",    30513, SLAVE_HSM, DataType.INT16, FC.FC4, level=Level.L3,
                description="Ladekreis D Betriebsmodus"),
    RegisterDef("hsm_pvstatus_bms", 30700, SLAVE_HSM, DataType.INT16, FC.FC4, level=Level.L3,
                description="PV-Status HSM intern ermittelt"),

    # HSM error management (Level 3, FC4)
    RegisterDef("hsm_warningbits",  35940, SLAVE_HSM, DataType.INT16, FC.FC4, level=Level.L3,
                description="Warnungs-Bitfeld (BIT0=HSM, BIT1=WPM1, ... BIT8=WPM8)"),
    RegisterDef("hsm_errorbits",    35941, SLAVE_HSM, DataType.INT16, FC.FC4, level=Level.L3,
                description="Störungs-Bitfeld (BIT0=HSM, BIT1=WPM1, ... BIT8=WPM8)"),
    RegisterDef("hsm_error_status", 35950, SLAVE_HSM, DataType.INT16, FC.FC4, level=Level.L3,
                description="HSM Fehlerstatus Bitfeld"),
    RegisterDef("hsm_error_quit",   35951, SLAVE_HSM, DataType.INT16, FC.FC4, level=Level.L3,
                writable=True,
                description="Störungen quittieren (BIT0=alle, BIT1=Ereignis, BIT2=Warnung, BIT3=Störung, BIT4=Störung+Sperre)"),
    RegisterDef("hsm_errorcode_1",  35960, SLAVE_HSM, DataType.INT16, FC.FC4, level=Level.L3,
                description="HSM Fehlercode 1"),
    RegisterDef("hsm_errorcode_2",  35961, SLAVE_HSM, DataType.INT16, FC.FC4, level=Level.L3,
                description="HSM Fehlercode 2"),
    RegisterDef("hsm_errorcode_3",  35962, SLAVE_HSM, DataType.INT16, FC.FC4, level=Level.L3,
                description="HSM Fehlercode 3"),
    RegisterDef("hsm_errorcode_4",  35963, SLAVE_HSM, DataType.INT16, FC.FC4, level=Level.L3,
                description="HSM Fehlercode 4"),
    RegisterDef("hsm_warningcode_1",35970, SLAVE_HSM, DataType.INT16, FC.FC4, level=Level.L3,
                description="HSM Warncode 1"),
    RegisterDef("hsm_warningcode_2",35971, SLAVE_HSM, DataType.INT16, FC.FC4, level=Level.L3,
                description="HSM Warncode 2"),

    # WW Level 3 BMS Input Registers (FC4) — duplicate of some L1/L2 via different address
    RegisterDef("ww_actualtempo_bms", 34014, SLAVE_HSM, DataType.FLOAT32, FC.FC4, level=Level.L3,
                unit="°C", description="WW Speichertemperatur Oben (BMS-Adresse, FC4)"),
    RegisterDef("ww_actualtempu_bms", 34016, SLAVE_HSM, DataType.FLOAT32, FC.FC4, level=Level.L3,
                unit="°C", description="WW Speichertemperatur Unten (BMS-Adresse, FC4)"),
    RegisterDef("ww_anfstatus_bms",   34019, SLAVE_HSM, DataType.INT16,   FC.FC4, level=Level.L3,
                description="WW-Anforderungsstatus (BMS-Adresse, FC4)"),

    # Puffer Level 3 (FC4)
    RegisterDef("hpuf_puot_bms",    35002, SLAVE_HSM, DataType.FLOAT32, FC.FC4, level=Level.L3,
                unit="°C", description="Heizungspuffer Istwert Oben (BMS-Adresse)"),
    RegisterDef("hpuf_puut_bms",    35004, SLAVE_HSM, DataType.FLOAT32, FC.FC4, level=Level.L3,
                unit="°C", description="Heizungspuffer Istwert Unten (BMS-Adresse)"),
    RegisterDef("hpuf_solltemp_bms",35015, SLAVE_HSM, DataType.FLOAT32, FC.FC4, level=Level.L3,
                unit="°C", description="Pufferspeicher Sollwert aktiv (BMS-Adresse)"),
    RegisterDef("hpuf_ladestatus_bms",35018, SLAVE_HSM, DataType.INT16,  FC.FC4, level=Level.L3,
                description="Puffer Ladestatus (BMS-Adresse)"),

    # Kühlpuffer Level 3 (FC4)
    RegisterDef("kpuf_puut_bms",    35204, SLAVE_HSM, DataType.FLOAT32, FC.FC4, level=Level.L3,
                requires_cooling=True, unit="°C", description="Kühlpuffer Istwert (BMS-Adresse)"),
    RegisterDef("kpuf_solltemp_bms",35215, SLAVE_HSM, DataType.FLOAT32, FC.FC4, level=Level.L3,
                requires_cooling=True, unit="°C", description="Kühlpuffer Sollwert aktiv (BMS-Adresse)"),
    RegisterDef("kpuf_ladestatus_bms",35218, SLAVE_HSM, DataType.INT16,  FC.FC4, level=Level.L3,
                requires_cooling=True, description="Kühlpuffer Ladestatus (BMS-Adresse)"),
]


# ---------------------------------------------------------------------------
# Build full register list based on user config
# ---------------------------------------------------------------------------

def build_register_list(
    level: Level,
    num_hk: int,
    num_wpm: int,
    has_ww_internal: bool,
    has_cooling: bool,
) -> list[RegisterDef]:
    """Return all applicable registers for the given configuration."""
    regs: list[RegisterDef] = []

    for reg in HSM_REGISTERS:
        if reg.level > level:
            continue
        if reg.requires_ww_internal and not has_ww_internal:
            continue
        if reg.requires_cooling and not has_cooling:
            continue
        regs.append(reg)

    # HK registers
    for n in range(1, min(num_hk, 4) + 1):
        hk_level = Level.L1 if n <= 2 else Level.L2
        if hk_level > level:
            continue
        regs.extend(_hk_registers_l1(n))
        if level >= Level.L2:
            for reg in _hk_registers_l2_ext(n):
                if reg.requires_cooling and not has_cooling:
                    continue
                regs.append(reg)

    # WPM registers
    for wpm in range(1, min(num_wpm, 8) + 1):
        regs.extend(_wpm_registers_l1(wpm))
        if level >= Level.L3:
            regs.extend(_wpm_registers_l3(wpm))

    return regs


# HK type options
HK_TYPE_OPTIONS = ["AUS", "Fußbodenheizung", "Heizkörper", "Pool"]
HK_TYPE_LABELS: dict[int, str] = {0: "AUS", 1: "Fußbodenheizung", 2: "Heizkörper", 3: "Pool"}

# ---------------------------------------------------------------------------
# WPM_STATUS code names (Level 3)
# ---------------------------------------------------------------------------

WPM_STATUS_NAMES: dict[int, str] = {
    0: "Störung",
    1: "Inverter Offline",
    3: "Sperrzeit",
    4: "Ölvorheizen",
    5: "Bereit",
    6: "Start",
    7: "WW",
    8: "Heizen",
    9: "Kühlen",
    10: "Abtauen",
    11: "Manuell Enteisen",
    12: "Stoppt",
    13: "Einsatzgrenze",
    14: "Inverter Reset",
}

# HK Mode names
HK_MODE_OPTIONS = ["AUS", "AUTOMATIK", "WINTER", "SOMMER"]
HK_FIX_MODE_OPTIONS = ["AUTO", "FIX_HEIZEN", "FIX_KUEHLEN"]

# EMS PV Status options
EMS_PV_STATUS_OPTIONS = ["Neutral", "Erhöhen", "Reduzieren"]

# ANF_MODE options (Level 3 BMS)
ANF_MODE_OPTIONS = ["HSM", "BMS_MOD_PERC", "BMS_MOD_TEMP", "BMS_AI_PERC", "BMS_AI_TEMP"]

# WW_ANFSTATUS names
WW_ANFSTATUS_NAMES: dict[int, str] = {
    0: "Keine Anforderung",
    1: "PLUS",
    2: "PV",
    3: "Legionellen",
    4: "Sollwert",
    5: "Turbo",
    6: "Frost",
}
