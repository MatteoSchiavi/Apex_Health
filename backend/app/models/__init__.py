"""ORM models."""

from app.models.activity import (
    Activity,
    ActivityLap,
    ActivitySourceLink,
    ActivityStream,
    Discipline,
)
from app.models.ai import AgentToolCall, AiReport, Embedding, TokenUsage
from app.models.alert import Alert
from app.models.base import Base
from app.models.challenge import Challenge, ChallengeMember
from app.models.chat import AiChatMessage, AiChatSession
from app.models.coach import SessionFeedback, UserContextDoc, UserEvent
from app.models.features import (
    DailyFeature,
    DisciplineFeature,
    FeatureWeight,
)
from app.models.integration import Integration, RawIngest
from app.models.gym import GymScheduleSlot
from app.models.gym_detail import (
    GymDayExercise,
    GymDayPlan,
    GymExercise,
    GymSetLog,
)
from app.models.gear import (
    ActivityGearLink,
    DisciplineGearDefault,
    Gear,
    GearServiceLog,
)
from app.models.journal import JournalEntry
from app.models.medical import (
    LabMetric,
    LabPanel,
    NutritionLog,
    SupplementLog,
    SupplementProtocol,
)
from app.models.telegram import TelegramLink, TelegramMessage
from app.models.training import PlannedSession, TrainingPlan
from app.models.user import AuthCredential, User, UserSession
from app.models.watch import DeviceToken
from app.models.weather import ForecastCache
from app.models.wellness import (
    DailyBiometric,
    HrvReading,
    SleepSession,
    StressReading,
)

__all__ = [
    "Activity",
    "ActivityLap",
    "ActivityGearLink",
    "ActivitySourceLink",
    "ActivityStream",
    "AgentToolCall",
    "AiChatMessage",
    "AiChatSession",
    "AiReport",
    "Alert",
    "AuthCredential",
    "Base",
    "Challenge",
    "ChallengeMember",
    "DailyBiometric",
    "DailyFeature",
    "DeviceToken",
    "Discipline",
    "DisciplineGearDefault",
    "DisciplineFeature",
    "Embedding",
    "FeatureWeight",
    "ForecastCache",
    "Gear",
    "GearServiceLog",
    "GymDayExercise",
    "GymDayPlan",
    "GymExercise",
    "GymScheduleSlot",
    "GymSetLog",
    "HrvReading",
    "Integration",
    "JournalEntry",
    "LabMetric",
    "LabPanel",
    "NutritionLog",
    "PlannedSession",
    "RawIngest",
    "SessionFeedback",
    "SleepSession",
    "StressReading",
    "SupplementLog",
    "SupplementProtocol",
    "TelegramLink",
    "TelegramMessage",
    "TokenUsage",
    "TrainingPlan",
    "User",
    "UserContextDoc",
    "UserEvent",
    "UserSession",
]
