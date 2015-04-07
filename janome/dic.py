# -*- coding: utf-8 -*-

import os
import pickle
import gzip, bz2
from struct import pack, unpack
from .fst import Matcher, create_minimum_transducer, compileFST
import traceback
import logging
import sys


# FILE_FST_DATA = 'fst.data'
# FILE_ENTRIES = 'entries.data'
# FILE_CONNECTIONS = 'connections.data'

MODULE_FST_DATA = 'fstdata.py'
MODULE_ENTRIES = 'entries.py'
MODULE_CONNECTIONS = 'connections.py'
MODULE_CHARDEFS = 'chardef.py'
MODULE_UNKNOWNS = 'unknowns.py'

FILE_USER_FST_DATA = 'user_fst.data'
FILE_USER_ENTRIES_DATA = 'user_entries.data'

def save_fstdata(data, dir='.'):
    #_save(os.path.join(dir, FILE_FST_DATA), data, compresslevel)
    _save_as_module(os.path.join(dir, MODULE_FST_DATA), data)


def save_entries(entries, dir='.'):
    #_save(os.path.join(dir, FILE_ENTRIES), pickle.dumps(entries), compresslevel)
    _save_as_module(os.path.join(dir, MODULE_ENTRIES), entries)


def save_connections(connections, dir='.'):
    #_save(os.path.join(dir, FILE_CONNECTIONS), pickle.dumps(connections), compresslevel)
    _save_as_module(os.path.join(dir, MODULE_CONNECTIONS), connections)


def save_chardefs(chardefs, dir='.'):
    _save_as_module(os.path.join(dir, MODULE_CHARDEFS), chardefs)


def save_unknowns(unknowns, dir='.'):
    _save_as_module(os.path.join(dir, MODULE_UNKNOWNS), unknowns)


def _save(file, data, compresslevel):
    if not data:
        return
    with gzip.open(file, 'wb', compresslevel) as f:
        f.write(data)
        f.flush()


def _load(file):
    if not os.path.exists(file):
        return None
    with gzip.open(file, 'rb') as f:
        data = f.read()
        return data


def _save_as_module(file, data):
    if not data:
        return
    with open(file, 'w') as f:
        f.write('DATA=')
        f.write(str(data))
        f.flush()


class Dictionary:
    """
    Base dictionary class
    """
    def __init__(self, compiledFST, entries, connections):
        self.compiledFST = compiledFST
        self.matcher = Matcher(compiledFST)
        self.entries = entries
        self.connections = connections

    def lookup(self, s):
        (matched, outputs) = self.matcher.run(s.encode('utf8'))
        if not matched:
            return []
        try:
            return [self.entries[unpack('I', e)[0]] for e in outputs]
        except Exception as e:
            logging.error('Cannot load dictionary data. The dictionary may be corrupted?')
            logging.error('input=%s' % s)
            logging.error('outputs=%s' % str(outputs))
            traceback.format_exc()
            sys.exit(1)

    def get_trans_cost(self, id1, id2):
        key = '%s,%s' % (id1, id2)
        return self.connections.get(key)


class SystemDictionary(Dictionary):
    """
    System dictionary class
    """
    def __init__(self, compiledFST, entries, connections, chardefs, unknowns):
        Dictionary.__init__(self, compiledFST, entries, connections)
        self.char_categories = chardefs[0]
        self.char_ranges = chardefs[1]
        self.unknowns = unknowns

    def char_category(self, c):
        for chr_range in self.char_ranges:
            if ord(c) in range(chr_range['from'], chr_range['to'] + 1):
                cate = chr_range['cate']
                compate_cates = chr_range['compat_cates'] if 'compat_cates' in chr_range else []
                return cate, compate_cates
        return None, None

    def unkown_invoked_always(self, cate):
        if cate in self.char_categories:
            return self.char_categories[cate]['INVOKE']
        return False

    def unknown_grouping(self, cate):
        if cate in self.char_categories:
            return self.char_categories[cate]['GROUP']
        return False

    def unknown_length(self, cate):
        if cate in self.char_categories:
            return self.char_categories[cate]['LENGTH']
        return -1


class UserDictionary(Dictionary):
    """
    User dictionary class (uncompiled)
    """
    def __init__(self, user_dict, enc, type, connections):
        build_method = getattr(self, 'build' + type)
        compiledFST, entries = build_method(user_dict, enc)
        Dictionary.__init__(self, compiledFST, entries, connections)

    def buildipadic(self, user_dict, enc):
        surfaces = []
        entries = {}
        with open(user_dict, encoding=enc) as f:
            for line in f:
                line = line.rstrip()
                surface, left_id, right_id, cost, \
                pos_major, pos_minor1, pos_minor2, pos_minor3, \
                infl_form, infl_type, base_form, reading, phonetic = \
                    line.split(',')
                part_of_speech = ','.join([pos_major, pos_minor1, pos_minor2, pos_minor3])
                morph_id = len(surfaces)
                surfaces.append((surface.encode('utf8'), pack('I', morph_id)))
                entries[morph_id] = (surface, left_id, right_id, int(cost), part_of_speech, infl_form, infl_type, base_form, reading, phonetic)
        inputs = sorted(surfaces)  # inputs must be sorted.
        assert len(surfaces) == len(entries)
        fst = create_minimum_transducer(inputs)
        compiledFST = compileFST(fst)
        return compiledFST, entries

    def save(self, to_dir, compressionlevel=9):
        if os.path.exists(to_dir) and not os.path.isdir(to_dir):
            raise Exception('Not a directory : %s' % to_dir)
        else:
            os.makedirs(to_dir, mode=0o755, exist_ok=True)
        _save(os.path.join(to_dir, FILE_USER_FST_DATA), self.compiledFST, compressionlevel)
        _save(os.path.join(to_dir, FILE_USER_ENTRIES_DATA), pickle.dumps(self.entries), compressionlevel)


class CompiledUserDictionary(Dictionary):
    """
    User dictionary class (compiled)
    """
    def __init__(self, dic_dir, connections):
        compiledFST, entries = self.load_dict(dic_dir)
        Dictionary.__init__(self, compiledFST, entries, connections)

    def load_dict(self, dic_dir):
        if not os.path.exists(dic_dir) or not os.path.isdir(dic_dir):
            raise FileNotFoundError('No such directory : ' % dic_dir)
        compiledFST = _load(os.path.join(dic_dir, FILE_USER_FST_DATA))
        entries = pickle.loads(_load(os.path.join(dic_dir, FILE_USER_ENTRIES_DATA)))
        return compiledFST, entries