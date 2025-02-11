import os.path
from typing import Optional, List, Dict, Any, Callable, Type, TYPE_CHECKING

import papis
import papis.plugin
import papis.logging


if TYPE_CHECKING:
    from stevedore import ExtensionManager


class Context:
    def __init__(self) -> None:
        self.data = {}   # type: Dict[str, Any]
        self.files = []  # type: List[str]

    def __bool__(self) -> bool:
        return bool(self.files) or bool(self.data)


class Importer:

    """This is the base class for every importer"""

    def __init__(self, uri: str = "", name: str = "",
                 ctx: Optional[Context] = None) -> None:
        """
        :param uri: uri
        :param name: Name of the importer
        """
        self.ctx = ctx or Context()  # type: Context
        self.uri = uri  # type: str
        self.name = name or os.path.basename(__file__)  # type: str
        self.logger = papis.logging.get_logger("papis.importer.{}".format(self.name))

    @classmethod
    def match(cls, uri: str) -> Optional["Importer"]:
        """This method should be called to know if a given uri matches
        the importer or not.

        For example, a valid match for archive would be:
        .. code:: python

            return re.match(r".*arxiv.org.*", uri)

        it will return something that is true if it matches and something
        falsely otherwise.

        :param uri: uri where the document should be retrieved from.
        """
        raise NotImplementedError(
            "Matching uri not implemented for this importer")

    @classmethod
    def match_data(cls, data: Dict[str, Any]) -> Optional["Importer"]:
        """Get a dictionary of data and try to decide if there is
        a valid uri in it.

        :param data: Data to look into
        """
        raise NotImplementedError(
            "Matching data not implemented for this importer")

    def fetch(self) -> None:
        """
        can return a dict to update the document with
        """
        from contextlib import suppress

        with suppress(NotImplementedError):
            self.fetch_data()

        with suppress(NotImplementedError):
            self.fetch_files()

    def fetch_data(self) -> None:
        raise NotImplementedError()

    def fetch_files(self) -> None:
        raise NotImplementedError()

    def __str__(self) -> str:
        return "Importer({}, uri={})".format(self.name, self.uri)


def _extension_name() -> str:
    return "papis.importer"


def get_import_mgr() -> "ExtensionManager":
    """Get the import manager
    :returns: Import manager
    """
    return papis.plugin.get_extension_manager(_extension_name())


def available_importers() -> List[str]:
    """Get the available importer names.
    :returns: List of importer names
    """
    return papis.plugin.get_available_entrypoints(_extension_name())


def get_importers() -> List[Type[Importer]]:
    """Get all available importers
    """
    return [e.plugin for e in get_import_mgr()]


def get_importer_by_name(name: str) -> Type[Importer]:
    """Get importer by name
    :param name: Name of the importer
    :returns: The importer
    """
    imp = get_import_mgr()[name].plugin  # type: Type[Importer]
    return imp


def cache(fun: Callable[[Importer], Any]) -> Callable[[Importer], Any]:
    """
    This is a decorator to be used if a method of an Importer
    is to be cached, i.e., if the context of the importer is already
    set, then one does not need to run the function anymore, even if
    it is explicitly run.

    :param self: Method of an Importer
    """
    def wrapper(self: Importer) -> Any:
        if not self.ctx:
            fun(self)
    return wrapper
