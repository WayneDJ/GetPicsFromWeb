#!/usr/bin/env python
# coding=utf-8

import inspect
import os
import re
import signal
import sys
import time
import zlib

import requests
from requests import ConnectionError
from utils.ConfigHelper import ConfigHelper
from utils.Logger import Logger

reload(sys)
sys.setdefaultencoding('utf-8')

__fileName__ = sys.argv[0]
currentPath = sys.path[0]
log = Logger.get(currentPath + '/utils/logging.conf')

# backup last running data in order to continue download
config = currentPath + '/config.data'
DataTemplate = {'caid': 1234, 'picid': 1233, 'catotal': 1235, 'catitle': 'this is a title sample', 'catag': 'xxx'}
configHelper = ConfigHelper(config)

indexUrl = 'https://www.nvshens.net'
headerStr = {
    'Referer': indexUrl,
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_0) AppleWebKit/537.36 (KHTML, like Gecko) '
                  'Chrome/76.0.3809.87 Safari/537.36 '
}
modelAlbumIndex = indexUrl + '/girl/'
basePath = currentPath + '/nvshens/'

# modelAlbumUrl = modelAlbumBase + modelID + '/album/'
mathchedTotalAlbum = 0  # type: int
maxReTryCount = 3


class TimeoutError:
    def __init__(self):
        pass


class PageNotFoundError:
    def __init__(self):
        pass


class StartNextLoopError:
    def __init__(self):
        pass


def getResponseEncoding(htmlText, isIndex):
    if isIndex is True:
        reg = 'charset=(.+?)" />'
    else:
        reg = '<meta charset="(.+?)">';
    charsetReg = re.compile(reg)
    charsetList = re.findall(charsetReg, htmlText)
    try:
        charset = charsetList[0]
    except IndexError:
        charset = 'utf-8'
    log.i(getCurrentFunName() + charset)
    return charset


def timeoutHandler():
    raise TimeoutError


def getAlbumResponse(albumUrl):
    """

    :type albumUrl: url string
    :param albumUrl: album url string
    """
    start = time.time();
    albumResponse = reTryGetResponse(albumUrl, isReTry=False)
    if albumResponse == '':
        log.i(getCurrentFunName() + 'Request Error handled , retry')
        albumResponse = reTryGetResponse(albumUrl)
    end = time.time()
    log.i(getCurrentFunName() + 'takes ' + elapsedSec(start, end))
    charset = getResponseEncoding(albumResponse.text, True)
    albumResponse.encoding = charset
    return albumResponse


def reTryGetResponse(albumUrl, headerStr=headerStr, retryInterval=80, isReTry=True):
    # type: (object, object, object, object) -> object
    """

    :type albumUrl:album url string
    :param headerStr:default request headerStr
    :param retryInterval: retry interval time
    :param isReTry: is retry or not
    """
    result = 'True'
    count = (2 if isReTry else 1)
    response = ''
    while result == 'True' and count < maxReTryCount:

        try:
            signal.signal(signal.SIGALRM, timeoutHandler)
            signal.alarm(retryInterval)
            start = time.time()  # type: float
            response = requests.get(albumUrl, headers=headerStr)
            result = 'False'
            signal.alarm(0)
        except TimeoutError:
            if isReTry:
                log.i(getCurrentFunName() + 'Requset TimeoutError handled , retry ' + str(count))
                count += 1
                continue
            else:
                return ''
        except ConnectionError:
            if isReTry:
                end = time.time()
                log.i(getCurrentFunName() + 'Request takes ' + elapsedSec(start, end)
                      + ' ConnectionError handled , retry ' + str(count))
                count += 1
                continue
            else:
                return ''
    if response == '':
        log.i(getCurrentFunName() + 'Null response ,exit')
        sys.exit()
    return response


def getAlbumTitle(htmlText):
    title = configHelper.get('catitle')
    reg = '<title>(.+?)</title>'
    titleReg = re.compile(reg)
    titleList = re.findall(titleReg, htmlText)
    if len(titleList) > 0:
        title = titleList[0].replace('-宅男女神图片', '')

    reg = '(\[.*?\])'
    titleReg = re.compile(reg)
    titleList = re.findall(titleReg, title)

    if len(titleList) > 0:
        title = title.replace(titleList[0], '')
    title = ''.join(title.split())
    try:
        title = title[:title.index("-")]
        if title.index('该页面未找到') >= 0:
            raise PageNotFoundError
    except ValueError:
        pass
    log.i(getCurrentFunName() + title)
    return title


def getAlbumMaxNum(htmlText):
    num = configHelper.get('catotal')
    reg = 'color: #DB0909\'>(.+?)</span>'
    numReg = re.compile(reg)
    numList = re.findall(numReg, htmlText)
    if len(numList) > 0:
        num = int(numList[0].replace('张照片', ''))
    log.i(getCurrentFunName() + str(num))
    return num


def getPicUrlTemplate(htmlText):
    reg = '<img\\b[^<>].*?\\bsrc[\\s\\t\\r\\n]*=[\\s\\t\\r\\n]*[\'|"]?[\\s\\t\\r\\n]*(.*?)' \
          '[\'|"]?[\\s\\t\\r\\n]*\\balt[\\s\\t\\r\\n]*=[\\s\\r\\t\\n]*[\'|"]?'
    urlReg = re.compile(reg)
    picUrlList = re.findall(urlReg, htmlText)
    picUrl = picUrlList[0]
    log.i(getCurrentFunName() + picUrl + str(len(picUrlList)) + '\n')
    return picUrl


def getPicNamePrefix(index):
    if index < 10:
        picNamePrefix = '00'
    elif index < 100:
        picNamePrefix = '0'
    elif index > 99:
        picNamePrefix = ''
    else:
        picNamePrefix = str(index)
    return picNamePrefix


def getNextPicUrl(picUrlTemplate, index, picType):
    nextPicUrl = picUrlTemplate
    picNamePrefix = getPicNamePrefix(index)
    if index != 0:
        nextPicUrl = picUrlTemplate.replace('0.' + picType, picNamePrefix + str(index) + '.' + picType)
    log.i(getCurrentFunName() + nextPicUrl)
    return nextPicUrl


def formatSize(bytesNum):
    try:
        bytesNum = float(bytesNum)
        kb = bytesNum / 1024
    except:
        return "Error"
    if kb >= 1024:
        M = kb / 1024
        if M >= 1024:
            G = M / 1024
            return '%.2fG' % G
        else:
            return '%.2fM' % M
    else:
        return '%.2fkb' % kb


def getPicContent(picUrl):
    """

    :type picUrl: pic url
    """
    start = time.time()
    log.i(getCurrentFunName() + '...')
    picResponse = reTryGetResponse(picUrl, isReTry=False)
    if picResponse == '':
        log.i(getCurrentFunName() + 'Requset TimeoutError handled , retry')
        picResponse = reTryGetResponse(picUrl)
    try:
        picContent = picResponse.content
        reTryTime = 0
        while len(picContent) == 0:
            reTryTime += 1
            log.d(getCurrentFunName() + 'get ZERO pic content, retry ' + str(reTryTime))
            picContent = reTryGetResponse(picUrl)
            if reTryTime == maxReTryCount:
                log.i(getCurrentFunName() + 'over retry times, below not be download:')
                log.e(getCurrentFunName() + picUrl)
                break
        end = time.time()
        log.i(getCurrentFunName() + 'takes ' + elapsedSec(start, end))
        return picContent
    except TypeError:
        log.i(getCurrentFunName() + 'picResponse TypeError handled, return ZERO')
        # sys.exit()
        return picResponse.content


def savePic(fileName, picContent):
    picFile = open(fileName, 'wb')
    picFile.write(picContent)
    picFile.close()
    log.i(getCurrentFunName() + formatSize(len(picContent)) + ' to ...' + fileName[-15:] + '\n')


def saveAlbum(urlOfAlbum):
    """

    :type urlOfAlbum album url string
    """
    albumResponse = getAlbumResponse(urlOfAlbum)
    title = getAlbumTitle(albumResponse.text)
    albumMax = getAlbumMaxNum(albumResponse.text)
    albumTags = getModleAlbumTags(albumResponse.text)

    configHelper.set('catitle', title)
    configHelper.set('catotal', albumMax)
    configHelper.set('catag', albumTags)
    configHelper.save()

    tagsNameWanted = ['制服', '丝袜']
    tagMatched = False  # type: not matched is False
    for tag in albumTags:
        for iTag in tagsNameWanted:
            try:
                tagIndex = tag.index(iTag)
            except ValueError:
                tagIndex = -1
            if tagIndex >= 0:
                tagMatched = True
                log.i(getCurrentFunName() + tag + ' TARGET MATCHED')
                global mathchedTotalAlbum
                mathchedTotalAlbum += 1
                break
        else:
            continue
        break
    if not tagMatched:
        log.i(getCurrentFunName() + 'NOT TARGET, return\n')
        return

    startPid = configHelper.get('picid')
    picsTotal = configHelper.get('catotal')
    if startPid == '0':
        startPid = 0
    elif startPid < 0:
        raise StartNextLoopError
    elif startPid > 0:
        startPid += 1
    if (startPid != 0) and (picsTotal > startPid + 1):
        log.i(getCurrentFunName() + 'resume to download left ' + str(picsTotal - startPid) + ' pics')

    filePath = basePath + title + '/'
    if not os.path.exists(filePath):
        os.makedirs(filePath)
        log.i(getCurrentFunName() + 'Create directory ' + filePath)

    picUrlTemplate = getPicUrlTemplate(albumResponse.text)
    for i in range(startPid, albumMax):
        splitList = picUrlTemplate.split('.')
        fileExt = splitList[len(splitList) - 1]
        fileNameWithExt = str(configHelper.get('caid')) + '-'
        fileNameWithExt += getPicNamePrefix(i) + str(i) + '.' + fileExt
        picUrl = getNextPicUrl(picUrlTemplate, i, fileExt)
        picContent = getPicContent(picUrl)
        savePic(filePath + fileNameWithExt, picContent)
        configHelper.set('picid', i)
    configHelper.set('picid', -1)
    configHelper.save()
    log.i(getCurrentFunName() + 'Done ' + str(albumMax) + ' pics saved \n')


def elapsedSec(start, end):
    elapsed = end - start
    timeList = str(elapsed).split('.')
    minTime = timeList[0]
    secTime = timeList[1][:2]
    return minTime + '.' + secTime + 's'


def getModleAlbumTags(htmlText):
    reg = '<a target=\'_blank\' href=\'.*?\'>[\\s\\t\\r\\n]*(.*?)[\\s\\t\\r\\n]*</a>'
    tagsReg = re.compile(reg)
    tags = re.findall(tagsReg, htmlText)  # type: List[String]
    tagStr = ''
    for s in tags:
        tagStr += ' ' + s
    log.i(getCurrentFunName() + tagStr)
    return tags


def getCurrentFunName():
    name = inspect.stack()[1][3]
    if name == '<module>':
        name = __name__
    return __fileName__ + '>:' + name + ' '


if __name__ == '__main__':
    albumIdMax = 30815
    configCAID = configHelper.get('caid')
    albumId = (albumIdMax if (configCAID == '0') else configCAID)
    windowSize = 65
    albumIdMax = albumId + windowSize
    count = 0
    while albumId <= albumIdMax:
        try:
            albumUrl = indexUrl + '/g/' + str(albumId)
            log.i(getCurrentFunName() + 'Start request ' + albumUrl)
            caId = configHelper.get('caid')
            configHelper.set('caid', albumId)
            picId = configHelper.get('picid')
            if caId == '0':
                caId = 0
            if (albumId != caId) or (picId == '0'):
                configHelper.set('picid', 0)
            saveAlbum(str(albumUrl))
        except IndexError:
            log.i(getCurrentFunName() + 'IndexError : 404\n')
        except KeyboardInterrupt:
            log.i(getCurrentFunName() + 'KeyboardInterrupt, just stop\n')
            sys.exit(0)
        except PageNotFoundError:
            count += 1
            log.i(getCurrentFunName() + 'PageNotFoundError ' + str(count) + '\n')
            if count > 2:
                configHelper.set('caid', albumId - count)
                configHelper.set('picid', -1)
                configHelper.save()
                sys.exit(0)
        except StartNextLoopError:
            log.i(getCurrentFunName() + 'Current album done, return\n')
            albumId += 1
            continue
        albumId += 1
        time.sleep(2)
log.i(getCurrentFunName() + 'All Finished, download album ' + str(mathchedTotalAlbum))
