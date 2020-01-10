# -*- coding: utf-8 -*-
"""
This file contains the Qudi configuration file module.

A configuration file is saved in YAML format. This module provides a loader
and a dumper using an OrderedDict instead of the regular dict used by PyYAML.
Additionally, it fixes a bug in PyYAML with scientific notation and allows
to dump numpy dtypes and numpy ndarrays.

The fix of the scientific notation is applied globally at module import.

The idea of the implementation of the OrderedDict was taken from
http://stackoverflow.com/questions/5121931/in-python-how-can-you-load-yaml-mappings-as-ordereddicts



Qudi is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Qudi is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with Qudi. If not, see <http://www.gnu.org/licenses/>.

Copyright (c) the Qudi Developers. See the COPYRIGHT.txt file at the
top-level directory of this distribution and at <https://github.com/Ulm-IQO/qudi/>
"""

from collections import OrderedDict
import numpy
import re
import os
import ruamel.yaml as yaml
from io import BytesIO


def ordered_load(stream, loader_base=yaml.Loader):
    """
    Loads a YAML formatted data from stream and puts it into an OrderedDict

    @param Stream stream: stream the data is read from
    @param yaml.Loader loader_base: YAML Loader base class

    @return OrderedDict: Dict containing data. If stream is empty then an empty dict is returned
    """
    class OrderedLoader(loader_base):
        """
        Loader using an OrderedDict
        """
        pass

    def construct_mapping(loader, node):
        """
        The OrderedDict constructor.
        """
        loader.flatten_mapping(node)
        return OrderedDict(loader.construct_pairs(node))

    def construct_ndarray(loader, node):
        """
        The ndarray constructor, correctly saves a numpy array inside the config file as a string.
        """
        value = loader.construct_yaml_binary(node)
        with BytesIO(bytes(value)) as f:
            arrays = numpy.load(f)
            return arrays['array']

    def construct_external_ndarray(loader, node):
        """
        The constructor for an numpy array that is saved in an external file.
        """
        filename = loader.construct_yaml_str(node)
        arrays = numpy.load(filename)
        return arrays['array']

    def construct_frozenset(loader, node):
        """
        The frozenset constructor.
        """
        data = tuple(loader.construct_yaml_set(node))
        return frozenset(data[0]) if data else frozenset()

    def construct_str(loader, node):
        """
        construct strings but if the string starts with 'array(' it tries
        to evaluate it as numpy array.

        TODO: This behaviour should be deprecated at some point.
        """
        value = loader.construct_yaml_str(node)
        # if a string could be an array, we try to evaluate the string
        # to reconstruct a numpy array. If it fails we return the string.
        if value.startswith('array('):
            try:
                local = {"array": numpy.array}
                for dtype in ['int8', 'uint8', 'int16', 'uint16', 'float16', 'int32', 'uint32',
                              'float32', 'int64', 'uint64', 'float64']:
                    local[dtype] = getattr(numpy, dtype)
                return eval(value, local)
            except SyntaxError:
                return value
        else:
            return value

    # add constructors
    OrderedLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, construct_mapping)
    OrderedLoader.add_constructor('!ndarray', construct_ndarray)
    OrderedLoader.add_constructor('!extndarray', construct_external_ndarray)
    OrderedLoader.add_constructor('!frozenset', construct_frozenset)
    OrderedLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_SCALAR_TAG, construct_str)

    # load config file
    config = yaml.load(stream, OrderedLoader)
    # yaml returns None if the config file was empty
    return OrderedDict() if config is None else config


def ordered_dump(data, stream=None, dumper_base=yaml.Dumper, **kwargs):
    """
    Dumps OrderedDict data into a YAML format stream

    @param OrderedDict data: the data to dump
    @param Stream stream: stream to dump the data into (in YAML)
    @param yaml.Dumper dumper_base: The dumper that is used as a base class
    """
    class OrderedDumper(dumper_base):
        """
        A Dumper using an OrderedDict
        """
        external_ndarray_counter = 0

        def ignore_aliases(self, ignore_data):
            """
            ignore aliases and anchors
            """
            return True

    def represent_ordereddict(dumper, data):
        """
        Representer for OrderedDict
        """
        return dumper.represent_mapping(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
                                        data.items())

    def represent_int(dumper, data):
        """
        Representer for numpy int dtypes
        """
        return dumper.represent_int(numpy.asscalar(data))

    def represent_float(dumper, data):
        """
        Representer for numpy float dtypes
        """
        return dumper.represent_float(numpy.asscalar(data))

    def represent_frozenset(dumper, data):
        """
        Representer for frozenset
        """
        node = dumper.represent_set(set(data))
        node.tag = '!frozenset'
        return node

    def represent_ndarray(dumper, data):
        """
        Representer for numpy ndarrays
        """
        try:
            filename = os.path.splitext(os.path.basename(stream.name))[0]
            configdir = os.path.dirname(stream.name)
            newpath = '{0}-{1:06}.npz'.format(os.path.join(configdir, filename),
                                              dumper.external_ndarray_counter)
            numpy.savez_compressed(newpath, array=data)
            node = dumper.represent_str(newpath)
            node.tag = '!extndarray'
            dumper.external_ndarray_counter += 1
        except:
            with BytesIO() as f:
                numpy.savez_compressed(f, array=data)
                compressed_string = f.getvalue()
            node = dumper.represent_binary(compressed_string)
            node.tag = '!ndarray'
        return node

    # add representers
    OrderedDumper.add_representer(OrderedDict, represent_ordereddict)
    OrderedDumper.add_representer(numpy.uint8, represent_int)
    OrderedDumper.add_representer(numpy.uint16, represent_int)
    OrderedDumper.add_representer(numpy.uint32, represent_int)
    OrderedDumper.add_representer(numpy.uint64, represent_int)
    OrderedDumper.add_representer(numpy.int8, represent_int)
    OrderedDumper.add_representer(numpy.int16, represent_int)
    OrderedDumper.add_representer(numpy.int32, represent_int)
    OrderedDumper.add_representer(numpy.int64, represent_int)
    OrderedDumper.add_representer(numpy.float16, represent_float)
    OrderedDumper.add_representer(numpy.float32, represent_float)
    OrderedDumper.add_representer(numpy.float64, represent_float)
    # OrderedDumper.add_representer(numpy.float128, represent_float)
    OrderedDumper.add_representer(numpy.ndarray, represent_ndarray)
    OrderedDumper.add_representer(frozenset, represent_frozenset)

    # dump data
    return yaml.dump(data, stream, OrderedDumper, **kwargs)


def load(file_path, ignore_missing=False):
    """
    Loads a config file. Throws a FileNotFoundError if the file does not exist

    @param str file_path: path to config file
    @param bool ignore_missing: Optional flag to suppress FileNotFoundError

    @return OrderedDict: The data as python/numpy objects in an OrderedDict
    """
    if os.path.isfile(file_path):
        with open(file_path, 'r') as f:
            return ordered_load(f, yaml.SafeLoader)
    elif ignore_missing:
        return OrderedDict()
    raise FileNotFoundError('Could not load config file "{0}". File not found'.format(file_path))


def save(file_path, data):
    """
    Saves data to file_path in yaml format. Creates subdirectories if not already present.

    @param str file_path: path to config file to save
    @param OrderedDict data: config values
    """
    file_dir = os.path.dirname(file_path)
    if not os.path.exists(file_dir):
        os.makedirs(file_dir)
    with open(file_path, 'w') as f:
        ordered_dump(data, stream=f, dumper_base=yaml.SafeDumper, default_flow_style=False)
