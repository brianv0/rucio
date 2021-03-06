# Copyright European Organization for Nuclear Research (CERN)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# You may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# http://www.apache.org/licenses/LICENSE-2.0
#
# Authors:
# - Wen Guan, <wguan@cern.ch>, 2014-2016
# - Cedric Serfon, <cedric.serfon@cern.ch>, 2014-2016
# - Vincent Garonne, <vincent.garonne@cern.ch>, 2016
# - Mario Lassnig, <mario.lassnig@cern.ch>, 2016

import errno
import json
import os
import re
import urlparse

from rucio.common import exception, config
from rucio.rse.protocols import protocol

try:
    import gfal2
except:
    if not config.config_has_section('database'):
        raise exception.MissingDependency('Missing dependency : gfal2')


class Default(protocol.RSEProtocol):
    """ Implementing access to RSEs using the srm protocol."""

    def lfns2pfns(self, lfns):
        """
        Returns a fully qualified PFN for the file referred by path.

        :param path: The path to the file.

        :returns: Fully qualified PFN.
        """

        pfns = {}
        prefix = self.attributes['prefix']
        if self.attributes['extended_attributes'] is not None and 'web_service_path' in self.attributes['extended_attributes'].keys():
            web_service_path = self.attributes['extended_attributes']['web_service_path']
        else:
            web_service_path = ''

        if not prefix.startswith('/'):
            prefix = ''.join(['/', prefix])
        if not prefix.endswith('/'):
            prefix = ''.join([prefix, '/'])

        hostname = self.attributes['hostname']
        if '://' in hostname:
            hostname = hostname.split("://")[1]

        lfns = [lfns] if type(lfns) == dict else lfns
        if self.attributes['port'] == 0:
            for lfn in lfns:
                scope, name = lfn['scope'], lfn['name']
                path = lfn['path'] if 'path' in lfn and lfn['path'] else self._get_path(scope=scope, name=name)
                if path.startswith('/'):
                    path = path[1:]
                pfns['%s:%s' % (scope, name)] = ''.join([self.attributes['scheme'], '://', hostname, web_service_path, prefix, path])
        else:
            for lfn in lfns:
                scope, name = lfn['scope'], lfn['name']
                path = lfn['path'] if 'path' in lfn and lfn['path'] else self._get_path(scope=scope, name=name)
                if path.startswith('/'):
                    path = path[1:]
                pfns['%s:%s' % (scope, name)] = ''.join([self.attributes['scheme'], '://', hostname, ':', str(self.attributes['port']), web_service_path, prefix, path])

        return pfns

    def parse_pfns(self, pfns):
        """
        Splits the given PFN into the parts known by the protocol. During parsing the PFN is also checked for
        validity on the given RSE with the given protocol.

        :param pfn: a fully qualified PFN

        :returns: a dict containing all known parts of the PFN for the protocol e.g. scheme, path, filename

        :raises RSEFileNameNotSupported: if the provided PFN doesn't match with the protocol settings
        """

        ret = dict()
        pfns = [pfns] if ((type(pfns) == str) or (type(pfns) == unicode)) else pfns
        for pfn in pfns:
            parsed = urlparse.urlparse(pfn)
            if parsed.path.startswith('/srm/managerv2') or parsed.path.startswith('/srm/managerv1') or parsed.path.startswith('/srm/v2/server'):
                scheme, hostname, port, service_path, path = re.findall(r"([^:]+)://([^:/]+):?(\d+)?([^:]+=)?([^:]+)", pfn)[0]
            else:
                scheme = parsed.scheme
                hostname = parsed.netloc.partition(':')[0]
                port = parsed.netloc.partition(':')[2]
                path = parsed.path
                service_path = ''

            if self.attributes['hostname'] != hostname and self.attributes['hostname'] != scheme + "://" + hostname:
                raise exception.RSEFileNameNotSupported('Invalid hostname: provided \'%s\', expected \'%s\'' % (hostname, self.attributes['hostname']))

            if port != '' and str(self.attributes['port']) != str(port):
                raise exception.RSEFileNameNotSupported('Invalid port: provided \'%s\', expected \'%s\'' % (port, self.attributes['port']))
            elif port == '':
                port = self.attributes['port']

            if not path.startswith(self.attributes['prefix']):
                raise exception.RSEFileNameNotSupported('Invalid prefix: provided \'%s\', expected \'%s\'' % ('/'.join(path.split('/')[0:len(self.attributes['prefix'].split('/')) - 1]),
                                                                                                              self.attributes['prefix']))  # len(...)-1 due to the leading '/
            # Spliting path into prefix, path, filename
            prefix = self.attributes['prefix']
            path = path.partition(self.attributes['prefix'])[2]
            name = path.split('/')[-1]
            path = path.partition(name)[0]
            if not path.startswith('/'):
                path = '/' + path
            ret[pfn] = {'scheme': scheme, 'port': port, 'hostname': hostname, 'path': path, 'name': name, 'prefix': prefix, 'web_service_path': service_path}

        return ret

    def path2pfn(self, path):
        """
        Returns a fully qualified PFN for the file referred by path.

        :param path: The path to the file.

        :returns: Fully qualified PFN.
        """

        if '://' in path:
            return path

        hostname = self.attributes['hostname']
        if '://' in hostname:
            hostname = hostname.split("://")[1]

        if 'extended_attributes' in self.attributes.keys() and self.attributes['extended_attributes'] is not None and 'web_service_path' in self.attributes['extended_attributes'].keys():
            web_service_path = self.attributes['extended_attributes']['web_service_path']
        else:
            web_service_path = ''

        if not path.startswith('srm'):
            if self.attributes['port'] > 0:
                return ''.join([self.attributes['scheme'], '://', hostname, ':', str(self.attributes['port']), web_service_path, path])
            else:
                return ''.join([self.attributes['scheme'], '://', hostname, web_service_path, path])
        else:
            return path

    def connect(self):
        """
        Establishes the actual connection to the referred RSE.
        If we decide to use gfal, init should be done here.

        :raises RSEAccessDenied
        """

        self.__ctx = gfal2.creat_context()
        self.__ctx.set_opt_string_list("SRM PLUGIN", "TURL_PROTOCOLS", ["gsiftp", "rfio", "gsidcap", "dcap", "kdcap"])

    def get(self, path, dest):
        """
        Provides access to files stored inside connected the RSE.

        :param path: Physical file name of requested file
        :param dest: Name and path of the files when stored at the client

        :raises DestinationNotAccessible: if the destination storage was not accessible.
        :raises ServiceUnavailable: if some generic error occured in the library.
        :raises SourceNotFound: if the source file was not found on the referred storage.
        """

        dest = os.path.abspath(dest)
        if ':' not in dest:
            dest = "file://" + dest

        try:
            status = self.__gfal2_copy(path, dest)
            if status:
                raise exception.RucioException()
        except exception.DestinationNotAccessible as error:
            raise exception.DestinationNotAccessible(str(error))
        except exception.SourceNotFound as error:
            raise exception.SourceNotFound(str(error))
        except Exception as error:
            raise exception.ServiceUnavailable(error)

    def put(self, source, target, source_dir):
        """
        Allows to store files inside the referred RSE.

        :param source: path to the source file on the client file system
        :param target: path to the destination file on the storage
        :param source_dir: Path where the to be transferred files are stored in the local file system

        :raises DestinationNotAccessible: if the destination storage was not accessible.
        :raises ServiceUnavailable: if some generic error occured in the library.
        :raises SourceNotFound: if the source file was not found on the referred storage.
        """

        source_url = '%s/%s' % (source_dir, source) if source_dir else source

        source_url = os.path.abspath(source_url)
        if not os.path.exists(source_url):
            raise exception.SourceNotFound()
        if ':' not in source_url:
            source_url = "file://" + source_url

        space_token = None
        if self.attributes['extended_attributes'] is not None and 'space_token' in self.attributes['extended_attributes'].keys():
            space_token = self.attributes['extended_attributes']['space_token']

        try:
            status = self.__gfal2_copy(str(source_url), str(target), None, space_token)
            if status:
                raise exception.RucioException()
        except exception.DestinationNotAccessible as error:
            raise exception.DestinationNotAccessible(str(error))
        except exception.SourceNotFound as error:
            raise exception.DestinationNotAccessible(str(error))
        except Exception as error:
            raise exception.ServiceUnavailable(error)

    def delete(self, path):
        """
        Deletes a file from the connected RSE.

        :param path: path to the to be deleted file

        :raises ServiceUnavailable: if some generic error occured in the library.
        :raises SourceNotFound: if the source file was not found on the referred storage.
        """

        pfns = [path] if ((type(path) == str) or (type(path) == unicode)) else path

        try:
            status = self.__gfal2_rm(pfns)
            if status:
                raise exception.RucioException()
        except exception.SourceNotFound as error:
            raise exception.SourceNotFound(str(error))
        except Exception as error:
            raise exception.ServiceUnavailable(error)

    def rename(self, path, new_path):
        """
        Allows to rename a file stored inside the connected RSE.

        :param path: path to the current file on the storage
        :param new_path: path to the new file on the storage

        :raises DestinationNotAccessible: if the destination storage was not accessible.
        :raises ServiceUnavailable: if some generic error occured in the library.
        :raises SourceNotFound: if the source file was not found on the referred storage.
        """

        try:
            status = self.__gfal2_rename(path, new_path)
            if status:
                raise exception.RucioException()
        except exception.DestinationNotAccessible as error:
            raise exception.DestinationNotAccessible(str(error))
        except exception.SourceNotFound as error:
            raise exception.SourceNotFound(str(error))
        except Exception as error:
            raise exception.ServiceUnavailable(error)

    def exists(self, path):
        """
        Checks if the requested file is known by the referred RSE.

        :param path: Physical file name

        :returns: True if the file exists, False if it doesn't

        :raises SourceNotFound: if the source file was not found on the referred storage.
        """

        try:
            status = self.__gfal2_exist(path)
            if status:
                return False
            return True
        except exception.SourceNotFound as error:
            return False
        except Exception as error:
            raise exception.ServiceUnavailable(error)

    def close(self):
        """
        Closes the connection to RSE.
        """

        del self.__ctx
        self.__ctx = None

    def __gfal2_copy(self, src, dest, src_spacetoken=None, dest_spacetoken=None):
        """
        Uses gfal2 to copy file from src to dest.

        :param src: Physical source file name
        :param src_spacetoken: The source file's space token
        :param dest: Physical destination file name
        :param dest_spacetoken: The destination file's space token

        :returns: 0 if copied successfully, other than 0 if failed

        :raises SourceNotFound: if source file cannot be found.
        :raises RucioException: if it failed to copy the file.
        """

        ctx = self.__ctx
        params = ctx.transfer_parameters()
        if src_spacetoken:
            params.src_spacetoken = str(src_spacetoken)
        if dest_spacetoken:
            params.dst_spacetoken = str(dest_spacetoken)
        params.timeout = 3600

        dir_name = os.path.dirname(dest)
        # This function will be removed soon. gfal2 will create parent dir automatically.
        try:
            ctx.mkdir_rec(str(dir_name), 0775)
        except:
            pass

        try:
            ret = ctx.filecopy(params, str(src), str(dest))
            return ret
        except gfal2.GError as error:
            if error.code == errno.ENOENT or 'No such file' in error.message:
                raise exception.SourceNotFound(error)
            raise exception.RucioException(error)

    def __gfal2_rm(self, paths):
        """
        Uses gfal2 to remove the file.

        :param path: Physical file name

        :returns: 0 if removed successfully, other than 0 if failed

        :raises SourceNotFound: if the source file was not found.
        :raises RucioException: if it failed to remove the file.
        """

        ctx = self.__ctx

        try:
            for path in paths:
                ret = ctx.unlink(str(path))
                if ret:
                    return ret
            return ret
        except gfal2.GError as error:
            if error.code == errno.ENOENT or 'No such file' in error.message:
                raise exception.SourceNotFound(error)
            raise exception.RucioException(error)

    def __gfal2_exist(self, path):
        """
        Uses gfal2 to check whether the file exists.

        :param path: Physical file name

        :returns: 0 if it exists, -1 if it doesn't

        :raises RucioException: if the error is not source not found.
        """

        ctx = self.__ctx

        try:
            if ctx.stat(str(path)):
                return 0
            return -1
        except gfal2.GError as error:
            if error.code == errno.ENOENT or 'No such file' in error.message:
                return -1
            raise exception.RucioException(error)

    def __gfal2_rename(self, path, new_path):
        """
        Uses gfal2 to rename a file.

        :param path: path to the current file on the storage
        :param new_path: path to the new file on the storage

        :returns: 0 if it exists, -1 if it doesn't

        :raises RucioException: if failed.
        """

        ctx = self.__ctx

        try:
            dir_name = os.path.dirname(new_path)
            # This function will be removed soon. gfal2 will create parent dir automatically.
            try:
                ctx.mkdir_rec(str(dir_name), 0775)
            except Exception:
                pass
            ret = ctx.rename(str(path), str(new_path))
            return ret
        except gfal2.GError as error:
            if error.code == errno.ENOENT or 'No such file' in error.message:
                raise exception.SourceNotFound(error)
            raise exception.RucioException(error)

    def get_space_usage(self):
        """
        Get RSE space usage information.

        :returns: a list with dict containing 'totalsize' and 'unusedsize'

        :raises ServiceUnavailable: if some generic error occured in the library.
        """
        endpoint_basepath = self.path2pfn(self.attributes['prefix'])
        space_token = None
        if self.attributes['extended_attributes'] is not None and 'space_token' in self.attributes['extended_attributes'].keys():
            space_token = self.attributes['extended_attributes']['space_token']

        if space_token is None or space_token == "":
            raise exception.RucioException("Space token is not defined for protocol: %s" % (self.attributes['scheme']))

        try:
            totalsize, unusedsize = self.__gfal2_get_space_usage(endpoint_basepath, space_token)
            return totalsize, unusedsize
        except Exception as error:
            raise exception.ServiceUnavailable(error)

    def __gfal2_get_space_usage(self, path, space_token):
        """
        Uses gfal2 to get space usage info with space token.

        :param path: the endpoint path
        :param space_token: a string space token. E.g. "ATLASDATADISK"

        :returns: a list with dict containing 'totalsize' and 'unusedsize'

        :raises ServiceUnavailable: if failed.
        """

        ctx = self.__ctx

        try:
            ret_usage = ctx.getxattr(str(path), str("spacetoken.description?" + space_token))
            usage = json.loads(ret_usage)
            totalsize = usage[0]["totalsize"]
            unusedsize = usage[0]["unusedsize"]
            return totalsize, unusedsize
        except gfal2.GError as error:
            raise Exception(str(error))
