import uuid
from enum import Enum
from typing import List, Optional
from dataclasses import dataclass, field

# =============================================================================
# PARAMETERS
# =============================================================================

SIMULATION_STEPS = 365  # STEP (DAYS)

CRATE_TYPE_NAMES = ['TYPE_1', 'TYPE_2', 'TYPE_3', 'TYPE_4']
UL_SIZE = 200  # RTI
TRUCK_CAPACITY = 33  # UL

PRO_REORDER_POINT = 5000  # RTI
PRO_REORDER_QTY = 1 * TRUCK_CAPACITY  # UL
PRO_ORDER_LT = 1  # STEP
WASHING_REQUIREMENT_RATE = 0.50  # %

RDC_DAILY_DEMAND_MEAN = 7000  # RTI
RDC_DAILY_DEMAND_STD = 1000  # RTI

RPOS_DISPLAY_TIME = {'big': 1, 'medium': 1, 'small': 2}  # STEPS

RTI_BREAKAGE_RATE = 0.05  # %
POOL_SCREENING_CAPACITY = 20  # UL
POOL_PROCESSING_TIME = 1  # STEP

POOLER = "POOL_1"
PRODUCERS = [
    {"id": "PRO_1", "product": "Orange", "makes_dirty": False, "compatible_crates": ['TYPE_1', 'TYPE_3']},
    {"id": "PRO_2", "product": "Lemon", "makes_dirty": False, "compatible_crates": ['TYPE_2', 'TYPE_4']},
    {"id": "PRO_3", "product": "Apple", "makes_dirty": False, "compatible_crates": ['TYPE_3', 'TYPE_4']},
    {"id": "PRO_4", "product": "Banana", "makes_dirty": True, "compatible_crates": ['TYPE_2', 'TYPE_3']},
    {"id": "PRO_5", "product": "Peach", "makes_dirty": True, "compatible_crates": ['TYPE_1', 'TYPE_3']},
    {"id": "PRO_6", "product": "Plum", "makes_dirty": True, "compatible_crates": ['TYPE_2']},
    {"id": "PRO_7", "product": "Strawberry", "makes_dirty": True, "compatible_crates": ['TYPE_1', 'TYPE_4']}
]
RDC = "RDC_1"
N_RPOS_BIG = 5
N_RPOS_MEDIUM = 5
N_RPOS_SMALL = 10
N_RPOS = N_RPOS_BIG + N_RPOS_MEDIUM + N_RPOS_SMALL

INIT_POOL_WASHED_UL = 100  # UL
INIT_POOL_UNWASHED_UL = 100  # UL
INIT_PRO_UL = 50  # UL
INIT_RDC_UL = 15  # UL
INIT_RPOS_RTI = 260  # RTI

# =============================================================================
# DATA CLASSES & ENUMS
# =============================================================================

_crate_type_members = {name: name.lower() for name in CRATE_TYPE_NAMES}
CrateType = Enum('CrateType', _crate_type_members)
ALL_CRATE_TYPES = list(CrateType)


@dataclass(frozen=True)
class Product:
    name: str
    makes_dirty: bool
    compatible_crates: List[CrateType]


@dataclass
class OrderLine:
    issuer: str
    supplier: str
    order_id: str
    crate_type: CrateType
    quantity: int
    uom: str
    lead_time: int
    creation_step: int
    product: Optional[Product] = None
    needs_washed: Optional[bool] = None


@dataclass
class UnitLoad:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    crate_type: CrateType = field(default_factory=lambda: list(CrateType)[0])
    rtis: List['RTI_Agent'] = field(default_factory=list)  # type: ignore

    def add_rti(self, rti: 'RTI_Agent'):  # type: ignore
        self.rtis.append(rti)


class LocationType(Enum):
    POOL = "pool"
    PRO = "pro"
    R_DC = "r_dc"
    R_POS = "r_pos"
    TRANSPORT = "transport"
