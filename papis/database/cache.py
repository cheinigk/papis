import pickle
import logging
import os
import papis.utils
from papis.utils import get_cache_home, folders_to_documents
import papis.docmatcher
import papis.document
import papis.config
import papis.database.base
import re
import multiprocessing
import time


logger = logging.getLogger("cache")


def get_cache_file_name(directory):
    """Create a cache file name out of the path of a given directory.

    :param directory: Folder name to be used as a seed for the cache name.
    :type  directory: str
    :returns: Name for the cache file.
    :rtype:  str

    >>> get_cache_file_name('path/to/my/lib')
    'a8c689820a94babec20c5d6269c7d488-lib'
    >>> get_cache_file_name('papers')
    'a566b2bebc62611dff4cdaceac1a7bbd-papers'
    """
    import hashlib
    return "{}-{}".format(
        hashlib.md5(directory.encode()).hexdigest(),
        os.path.basename(directory)
    )


def get_cache_file_path(directory):
    """Get the full path to the cache file

    :param directory: Library folder
    :type  directory: str

    >>> import os; os.environ["XDG_CACHE_HOME"] = '/tmp'
    >>> get_cache_file_path('blah/papers')
    '/tmp/papis/database/c39177eca0eaea2e21134b0bd06631b6-papers'
    """
    cache_name = get_cache_file_name(directory)
    folder = os.path.expanduser(os.path.join(get_cache_home(), 'database'))
    if not os.path.exists(folder):
        os.makedirs(folder)
    return os.path.join(folder, cache_name)



def filter_documents(documents, search=""):
    """Filter documents. It can be done in a multi core way.

    :param documents: List of papis documents.
    :type  documents: papis.documents.Document
    :param search: Valid papis search string.
    :type  search: str
    :returns: List of filtered documents
    :rtype:  list

    >>> document = papis.document.from_data({'author': 'einstein'})
    >>> len(filter_documents([document], search="einstein")) == 1
    True
    >>> len(filter_documents([document], search="author = ein")) == 1
    True
    >>> len(filter_documents([document], search="title = ein")) == 1
    False

    """
    logger = logging.getLogger('filter')
    papis.docmatcher.DocMatcher.set_search(search)
    papis.docmatcher.DocMatcher.parse()
    papis.docmatcher.DocMatcher.set_matcher(match_document)
    if search == "" or search == ".":
        return documents
    else:
        # Doing this multiprocessing in filtering does not seem
        # to help much, I don't know if it's because I'm doing something
        # wrong or it is really like this.
        np = multiprocessing.cpu_count()
        pool = multiprocessing.Pool(np)
        logger.debug(
            "Filtering {} docs (search {}) using {} cores".format(
                len(documents),
                search,
                np
            )
        )
        logger.debug("pool started")
        begin_t = time.time()
        result = pool.map(
            papis.docmatcher.DocMatcher.return_if_match, documents
        )
        pool.close()
        pool.join()
        filtered_docs = [d for d in result if d is not None]
        logger.debug(
            "done ({} ms) ({} docs)".format(
                1000*time.time()-1000*begin_t,
                len(filtered_docs))
        )
        return filtered_docs



def match_document(document, search, match_format=None):
    """Main function to match document to a given search.

    :param document: Papis document
    :type  document: papis.document.Document
    :param search: A valid search string
    :type  search: str
    :param match_format: Python-like format string.
        (`see <
            https://docs.python.org/2/library/string.html#format-string-syntax
        >`_)
    :type  match_format: str
    :returns: Non false if matches, true-ish if it does match.

    >>> papis.config.set('match-format', '{doc[author]}')
    >>> document = papis.document.from_data({'author': 'einstein'})
    >>> match_document(document, 'e in') is None
    False
    >>> match_document(document, 'ee in') is None
    True
    >>> match_document(document, 'einstein', '{doc[title]}') is None
    True
    """
    match_format = match_format or papis.config.get("match-format")
    match_string = papis.utils.format_doc(match_format, document)
    regex = get_regex_from_search(search)
    return re.match(regex, match_string, re.IGNORECASE)


def get_regex_from_search(search):
    """Creates a default regex from a search string.

    :param search: A valid search string
    :type  search: str
    :returns: Regular expression
    :rtype: str

    >>> get_regex_from_search(' ein 192     photon')
    '.*.*ein.*192.*photon'
    """
    return r".*"+re.sub(r"\s+", ".*", search)


class Database(papis.database.base.Database):

    def __init__(self, library=None):
        papis.database.base.Database.__init__(self, library)
        self.logger = logging.getLogger('db:cache')
        self.documents = None
        self.initialize()

    def get_backend_name(self):
        return 'papis'

    def initialize(self):
        pass

    def get_documents(self):
        if self.documents is not None:
            return self.documents
        use_cache = papis.config.getboolean("use-cache")
        cache_path = self._get_cache_file_path()
        if use_cache and os.path.exists(cache_path):
            self.logger.debug(
                "Getting documents from cache in {0}".format(cache_path)
            )
            with open(cache_path, 'rb') as fd:
                self.documents = pickle.load(fd)
        else:
            self.logger.info('Indexing library, this might take a while')
            folders = sum([
                papis.utils.get_folders(d) for d in self.get_dirs()
            ], [])
            self.documents = folders_to_documents(folders)
            if use_cache:
                self.save()
        self.logger.debug(
            "Loaded documents ({} documents)".format(
                len(self.documents)
            )
        )
        return self.documents

    def add(self, document):
        docs = self.get_documents()
        self.logger.debug('adding ...')
        docs.append(document)
        assert(
            docs[-1].get_main_folder() == document.get_main_folder()
        )
        assert(os.path.exists(document.get_main_folder()))
        self.save()

    def update(self, document):
        if not papis.config.getboolean("use-cache"):
            return
        docs = self.get_documents()
        self.logger.debug('updating document')
        result = self._locate_document(document)
        index = result[0][0]
        docs[index] = document
        self.save()

    def delete(self, document):
        if not papis.config.getboolean("use-cache"):
            return
        docs = self.get_documents()
        self.logger.debug('deleting document')
        result = self._locate_document(document)
        index = result[0][0]
        docs.pop(index)
        self.save()

    def match(self, document, query_string):
        return match_document(document, query_string)

    def clear(self):
        cache_path = self._get_cache_file_path()
        self.logger.warning("clearing cache %s " % cache_path)
        if os.path.exists(cache_path):
            os.remove(cache_path)

    def query_dict(self, dictionary):
        query_string = " ".join(
            ["{}=\"{}\" ".format(key, val) for key, val in dictionary.items()]
        )
        return self.query(query_string)

    def query(self, query_string):
        self.logger.debug('Querying')
        docs = self.get_documents()
        return filter_documents(docs, query_string)

    def get_all_query_string(self):
        return '.'

    def get_all_documents(self):
        return self.query(self.get_all_query_string())

    def save(self):
        cache_home = get_cache_home()
        if not os.path.exists(cache_home):
            self.logger.debug("Creating cache dir %s " % cache_home)
            os.makedirs(cache_home, mode=papis.config.getint('dir-umask'))

        docs = self.get_documents()
        self.logger.debug(
            'Saving ... ({} documents)'.format(len(docs))
        )
        path = self._get_cache_file_path()
        with open(path, "wb+") as fd:
            pickle.dump(docs, fd)

    def _get_cache_file_path(self):
        return get_cache_file_path(self.lib.path_format())

    def _locate_document(self, document):
        assert(isinstance(document, papis.document.Document))
        result = list(filter(
            lambda d: d[1].get_main_folder() == document.get_main_folder(),
            enumerate(self.get_documents())
        ))
        if len(result) == 0:
            raise Exception(
                'The document passed could not be found in the library'
            )
        return result
