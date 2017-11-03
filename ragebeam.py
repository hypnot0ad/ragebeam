#!/usr/bin/env python
"""
Usage:
  ragebeam.py <user_name:password> [windows | linux | solaris | freebsd | macos | aix ] <destination_folder>
"""

from docopt import docopt
import sys
import requests
import shutil
import os.path
from itertools import groupby
from BeautifulSoup import BeautifulSoup as soup


import logging
logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class RequestProgressWrapper():
    def __init__(self, obj):
        self.obj = obj
        self.total_size = float(obj.headers['content-length'].strip())
        self.bytes_so_far = 0

    def read(self, length):
        self.bytes_so_far += length
        percent = self.bytes_so_far / self.total_size
        percent = round(percent * 100, 2)
        percent = percent if percent < 100 else 100
        sys.stdout.write(
            "Downloaded %d of %d bytes (%0.f%%)\r" %
            (self.bytes_so_far, self.total_size, percent))
        sys.stdout.flush()
        return self.obj.read(length)

    def __del__(self):
        sys.stdout.write('\n')


class SlunkHelper(object):
    def __init__(
        self, username, password,
        login_url="https://login.splunk.com/page/checkauth",
        link_prefix='https://download.splunk.com/products/splunk/releases',
        page_url="https://www.splunk.com/en_us/download/splunk-enterprise.html"
    ):
        self.username = username
        self.password = password
        self.login_url = login_url
        self.link_prefix = link_prefix
        self.page_url = page_url
        self._links = None
        self.cookies = None

    def _log_in(self):
        logger.debug('logging in')
        responce = requests.post(
            self.login_url, auth=(self.username, self.password))
        if responce.status_code / 100 != 2:
            raise RuntimeError('Wasn\'t able to log in')
        self.cookies = responce.cookies
        logger.debug('logged in')
        print "Logged In"

    def _get_all_slunk_installer_links(self, page_text):
        logger.debug('Parsing page in search for links')
        html = soup(page_text)
        for tag in html.findAll('a', {'data-link': True}):
            link = tag.attrMap['data-link']
            logger.debug('Found link: %s' % link[:-4])
            if link.startswith(self.link_prefix):
                yield link

    def _get_links_from_page(self):
        logger.debug('getting links from the page')
        for i in range(15):
            responce = requests.get(self.page_url, cookies=self.cookies)
            links_list = list(
                self._get_all_slunk_installer_links(responce.text))
            if links_list:
                logger.debug('Links from the page are extracted!!!')
                break
            logger.info(
                'Attempt #%s to get links list from download page failed,'
                ' server has returned an empty page, retrying... ' % i)
        else:
            raise RuntimeError('Wasn\'t able to get links list')
        return links_list

    @property
    def links_grouped_by_os(self):
        logger.debug('Grouping links by OS')

        def group_func(x):
            return x.split(self.link_prefix, 1)[1].split('/')[-2]
        grouped_by_os_links = {
            k: list(g)
            for k, g in groupby(self.links, group_func)}
        logger.debug('Links are successfully grouped by OS')
        return grouped_by_os_links

    @property
    def links(self):
        if self._links is not None:
            return self._links
        self._log_in()
        self._links = self._get_links_from_page()
        self._links.sort()
        return self._links

    def download_link(self, url, destination_folder, silent=True):
        if self.cookies is None:
            self._log_in()
        print url.rsplit('/', 1)
        path = os.path.join(destination_folder, url.rsplit('/', 1)[1])
        print path
        logger.info('Downloading file "%s" to "%s"' % (url, path))
        responce = requests.get(url, cookies=self.cookies, stream=True)
        if responce.status_code / 100 != 2:
            raise RuntimeError('Can\'t download %s' % url)
        responce.raw.decode_content = True
        source = responce.raw if silent else RequestProgressWrapper(responce.raw)
        with open(path, 'wb') as destination:
            shutil.copyfileobj(source, destination)
        return path


if __name__ == '__main__':
    arguments = docopt(__doc__)
    username, password = arguments.pop('<user_name:password>').split(':', 1)
    destination_folder = arguments.pop('<destination_folder>')
    desired_os = ([k for k, v in arguments.items() if v] + [None])[0]
    splunk_helper = SlunkHelper(username, password)

    links = splunk_helper.links_grouped_by_os[desired_os] if desired_os else\
        splunk_helper.links

    message = '\n'.join(
        ["%s. %s" % (i, m.rsplit('/', 1)[1]) for i, m in enumerate(links)])

    message += '\nInput number of versions you would like to download: '
    link_num = int(raw_input(message))
    splunk_helper.download_link(
        links[link_num], destination_folder, silent=False)
