import os
import sqlite3
import logging

from appdirs import user_data_dir
try:
    from urllib.request import pathname2url
except ImportError:
    from urllib import pathname2url

from .interfaces import StoreInterface

log = logging.getLogger(__name__)
timeformat = "%Y%m%d-%H%M%S"


class SQLiteFile():
    """ This class ensures that the user's data is stored in its OS
        preotected user directory:

        **OSX:**

         * `~/Library/Application Support/<AppName>`

        **Windows:**

         * `C:\\Documents and Settings\\<User>\\Application Data\\Local Settings\\<AppAuthor>\\<AppName>`
         * `C:\\Documents and Settings\\<User>\\Application Data\\<AppAuthor>\\<AppName>`

        **Linux:**

         * `~/.local/share/<AppName>`

         Furthermore, it offers an interface to generated backups
         in the `backups/` directory every now and then.

         .. note:: The file name can be overwritten when providing a keyword
            argument ``profile``.
    """

    @classmethod
    def get_filename(self, **kwargs):
        appname = kwargs.get("appname", "graphene")

        if "profile" in kwargs:
            filename = "{}.sqlite".format(kwargs["profile"])
        else:
            filename = "{}.sqlite".format(appname)

        return filename

    @classmethod
    def get_path(self, *args, full=True, **kwargs):
        appauthor = kwargs.get("appauthor", "Fabian Schuh")
        appname = kwargs.get("appname", "graphene")
        data_dir = kwargs.get(
            "data_dir",
            user_data_dir(appname, appauthor))

        if not full:
            return data_dir

        filename = self.get_filename(**kwargs)

        return os.path.join(data_dir, filename)

    def __init__(self, *args, **kwargs):
        """ Initializes new storage object.

            No arguments are required. However, you may specify `path` to side-step
            the default/automatic path generation.

            If you *do* use, automatic path generation, `appname`, `appauthor` and
            `profile` can be used to adjust the result.

            You can also provide `data_dir`, so that the directory is specified
            by you (but the filename is still auto-generated).

            :param str path: Full path to database file (None by default)
            :param bool create: Create file if it does not exist (True by default)
            :param str appname: Application name (default is "graphene")
            :param str appauthor: Application author (default is "Fabian Schuh")
            :param str profile: Filename base (default is "graphene")
            :param str data_dir: Data dir to use (default is auto-generated)
        """
        if "path" in kwargs:
            self.sqlDataBaseFile = kwargs["path"]
            self.storageDatabase = os.path.basename(self.sqlDataBaseFile)
            data_dir = os.path.dirname(self.sqlDataBaseFile)
        else:
            cls = self.__class__
            self.sqlDataBaseFile = cls.get_path(full=True, **kwargs)
            self.storageDatabase = cls.get_filename(**kwargs)
            data_dir = cls.get_path(full=False, **kwargs)

        must_exist = not(kwargs.pop("create", True))
        if must_exist:
            try:
                dburi = 'file:{}?mode=rw'.format(pathname2url(self.sqlDataBaseFile))
                conn = sqlite3.connect(dburi, uri=True)
            except sqlite3.OperationalError:
                raise ValueError("Could not open file %s" % self.sqlDataBaseFile)

        #  Ensure that the directory in which the data is stored
        #     exists
        elif not(os.path.isdir(data_dir)):  # pragma: no cover
            os.makedirs(data_dir, exist_ok=True)


class SQLiteCommon(object):
    """ This class abstracts away common sqlite3 operations.

        This class should not be used directly.
    """
    def sql_fetchone(self, query):
        connection = sqlite3.connect(self.sqlDataBaseFile)
        cursor = connection.cursor()
        cursor.execute(*query)
        result = cursor.fetchone()
        connection.close()
        return result

    def sql_fetchall(self, query):
        connection = sqlite3.connect(self.sqlDataBaseFile)
        cursor = connection.cursor()
        cursor.execute(*query)
        results = cursor.fetchall()
        connection.close()
        return results

    def sql_execute(self, query, lastid=False):
        connection = sqlite3.connect(self.sqlDataBaseFile)
        cursor = connection.cursor()
        cursor.execute(*query)
        connection.commit()
        ret = None
        if lastid:
            cursor = connection.cursor()
            cursor.execute("SELECT last_insert_rowid();")
            ret = cursor.fetchone()[0]
        connection.close()
        return ret


class SQLiteStore(SQLiteFile, SQLiteCommon, StoreInterface):
    """ The SQLiteStore deals with the sqlite3 part of storing data into a
        database file.

        .. note:: This module is limited to two columns and merely stores
            key/value pairs into the sqlite database

        On first launch, the database file as well as the tables are created
        automatically.

        When inheriting from this class, the following three class members must
        be defined:

            * ``__tablename__``: Name of the table
            * ``__key__``: Name of the key column
            * ``__value__``: Name of the value column
    """

    #:
    __tablename__ = None
    __key__ = None
    __value__ = None

    def __init__(self, *args, **kwargs):
        #: Storage
        SQLiteFile.__init__(self, *args, **kwargs)
        StoreInterface.__init__(self, *args, **kwargs)
        if (
            self.__tablename__ is None or
            self.__key__ is None or
            self.__value__ is None
        ):
            raise ValueError(
                "Values missing for tablename, key, or value!"
            )
        if not self.exists():  # pragma: no cover
            self.create()

    def _haveKey(self, key):
        """ Is the key `key` available?
        """
        query = (
            "SELECT {} FROM {} WHERE {}=?".format(
                self.__value__,
                self.__tablename__,
                self.__key__
            ), (key,))
        return True if self.sql_fetchone(query) else False

    def __setitem__(self, key, value):
        """ Sets an item in the store

            :param str key: Key
            :param str value: Value
        """
        if self._haveKey(key):
            query = (
                "UPDATE {} SET {}=? WHERE {}=?".format(
                    self.__tablename__,
                    self.__value__,
                    self.__key__
                ), (value, key))
        else:
            query = (
                "INSERT INTO {} ({}, {}) VALUES (?, ?)".format(
                    self.__tablename__,
                    self.__key__,
                    self.__value__,
                ), (key, value))
        self.sql_execute(query)

    def __getitem__(self, key):
        """ Gets an item from the store as if it was a dictionary

            :param str value: Value
        """
        query = (
            "SELECT {} FROM {} WHERE {}=?".format(
                self.__value__,
                self.__tablename__,
                self.__key__
            ), (key,))
        result = self.sql_fetchone(query)
        if result:
            return result[0]
        else:
            if key in self.defaults:
                return self.defaults[key]
            else:
                return None

    def __iter__(self):
        """ Iterates through the store
        """
        return iter(self.keys())

    def keys(self):
        query = ("SELECT {} from {}".format(
            self.__key__,
            self.__tablename__), )
        return [x[0] for x in self.sql_fetchall(query)]

    def __len__(self):
        """ return lenght of store
        """
        query = ("SELECT id from {}".format(self.__tablename__), )
        return len(self.sql_fetchall(query))

    def __contains__(self, key):
        """ Tests if a key is contained in the store.

            May test againsts self.defaults

            :param str value: Value
        """
        if self._haveKey(key) or key in self.defaults:
            return True
        else:
            return False

    def items(self):
        """ returns all items off the store as tuples
        """
        query = ("SELECT {}, {} from {}".format(
            self.__key__,
            self.__value__,
            self.__tablename__), )
        r = []
        for key, value in self.sql_fetchall(query):
            r.append((key, value))
        return r

    def get(self, key, default=None):
        """ Return the key if exists or a default value

            :param str value: Value
            :param str default: Default value if key not present
        """
        if key in self:
            return self.__getitem__(key)
        else:
            return default

    # Specific for this library
    def delete(self, key):
        """ Delete a key from the store

            :param str value: Value
        """
        query = (
            "DELETE FROM {} WHERE {}=?".format(
                self.__tablename__,
                self.__key__
            ), (key,))
        self.sql_execute(query)

    def wipe(self):
        """ Wipe the store
        """
        query = ("DELETE FROM {}".format(self.__tablename__), )
        self.sql_execute(query)

    def exists(self):
        """ Check if the database table exists
        """
        query = ("SELECT name FROM sqlite_master " +
                 "WHERE type='table' AND name=?",
                 (self.__tablename__, ))
        return True if self.sql_fetchone(query) else False

    def create(self):  # pragma: no cover
        """ Create the new table in the SQLite database
        """
        query = ((
            """
            CREATE TABLE {} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                {} STRING(256),
                {} STRING(256)
            )"""
        ).format(
            self.__tablename__,
            self.__key__,
            self.__value__
        ), )
        self.sql_execute(query)
