import logging
from typing import Any, Dict, List, Optional, Callable, Iterator

from sqlalchemy.future import select

from .dtype_converters import DTypeConverter
from .setting_model import Setting
from ..async_settings_repository import AsyncSettingsRepository


class DBAsyncSettingsRepository(AsyncSettingsRepository):

    def __init__(self,
                 session_factory: Optional[Callable] = None,
                 dtype_converters: Optional[List[DTypeConverter]] = None) -> None:

        self._logger = logging.getLogger(self.__class__.__name__)
        self._logger.debug("Creating instance")

        self._db_session_factory = session_factory
        if dtype_converters is None:
            dtype_converters = []
        self._dtype_converters = dtype_converters.copy()

        self._logger.debug(f"Db session factory is set to {session_factory}; "
                           f"Set {len(dtype_converters)} converters")

    def set_db_session_factory(self, session_factory: Callable):
        self._logger.debug(f"Session factory is set to {session_factory}")
        self._db_session_factory = session_factory

    def set_dtype_converters(self, dtype_converters: List[DTypeConverter]):
        self._logger.debug(f"Set {len(dtype_converters)} converters")
        self._dtype_converters = dtype_converters.copy()

    async def get_one(self, setting_name: str) -> Any:
        self._logger.debug(f"Requested setting {setting_name}")

        async with self._db_session_factory() as session:
            statement = select(Setting).filter(Setting.name == setting_name)
            setting: Setting = (await session.execute(statement)).scalars().one()

        converted_setting = self._convert_one_setting_to_python_type(setting)
        return converted_setting

    async def set_one(self, setting_name: str, setting_value: Any) -> None:
        self._logger.debug(f"Setting {setting_name} is set to {setting_value}")

        converted_setting = self._convert_one_setting_to_db_format(setting_name, setting_value)
        async with self._db_session_factory() as session:
            await session.merge(converted_setting)
            await session.commit()

    async def get_many(self, setting_names: List[str]) -> Dict[str, Any]:
        self._logger.debug(f"Requested settings: {setting_names}")

        async with self._db_session_factory() as session:
            statement = select(Setting).filter(Setting.name.in_(setting_names))
            settings: Iterator[Setting] = (await session.execute(statement)).scalars().all()

        converted_settings = self._convert_settings_to_python_types(settings)
        return converted_settings

    async def set_many(self, settings: Dict[str, Any]) -> None:
        self._logger.debug("Set many settings is requested")

        converted_settings = self._convert_settings_to_db_format(settings)
        async with self._db_session_factory() as session:
            for setting in converted_settings:
                await session.merge(setting)
            await session.commit()

    async def get_all(self) -> Dict[str, Any]:
        self._logger.debug("All settings are requested")

        async with self._db_session_factory() as session:
            statement = select(Setting)
            settings: Iterator[Setting] = await session.execute(statement)

        converted_settings = self._convert_settings_to_python_types(settings)
        return converted_settings

    async def set_all(self, settings: Dict[str, Any]) -> None:
        self._logger.debug(f"Set all settings is requested")

        converted_settings = self._convert_settings_to_db_format(settings)
        async with self._db_session_factory() as session:
            statement = select(Setting)
            selected_settings = await session.execute(statement)
            await selected_settings.delete()
            for setting in converted_settings:
                await session.merge(setting)
            await session.commit()

    def _convert_settings_to_python_types(self, settings: Iterator[Setting]):
        self._logger.debug("Converting settings to python type")

        converted_settings = {}
        for setting in settings:
            converted_setting_value = self._convert_one_setting_to_python_type(setting)
            converted_settings[setting.name] = converted_setting_value

        self._logger.debug("Settings are converted")
        return converted_settings

    def _convert_one_setting_to_python_type(self, setting: Setting) -> Any:
        self._logger.debug(f"Converting setting to python type "
                           f"{setting.name}: {setting.type} = {setting.value}")

        for converter in self._dtype_converters:
            if converter.TYPE_NAME == setting.type:
                converted_value = converter.to_python_type(setting.value)
                break
        else:
            raise RuntimeError(f"Converter not found for type {setting.type}")

        return converted_value

    def _convert_settings_to_db_format(self, settings: Dict[str, Any]):
        self._logger.debug("Converting settings to db format")

        converted_settings = []
        for setting_name, setting_value in settings.items():
            converted_setting = self._convert_one_setting_to_db_format(setting_name, setting_value)
            converted_settings.append(converted_setting)

        self._logger.debug("Settings are converted")
        return converted_settings

    def _convert_one_setting_to_db_format(self, setting_name: str, setting_value: Any) -> Setting:
        self._logger.debug(f"Converting setting to db format "
                           f"{setting_name}: {type(setting_value)} = {setting_value}")

        for converter in self._dtype_converters:
            if isinstance(setting_value, converter.PYTHON_TYPE):
                converted_value = converter.to_db_format(setting_value)
                setting = Setting(name=setting_name, type=converter.TYPE_NAME, value=converted_value)
                break
        else:
            raise RuntimeError(f"Converter not found for type {type(setting_value)}")

        return setting
