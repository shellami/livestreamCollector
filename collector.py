import json
import urllib.request
import re
import sys
import os.path
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
import pprint
import time
import uuid
from time import gmtime, strftime
import requests

# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/youtube.readonly']
logFilePath = 'log.txt'
changeLogFilePath = 'changelog.txt'
sleepSeconds = 10

def uprint(*objects, sep=' ', end='\n', file=sys.stdout):
    enc = file.encoding
    if enc == 'UTF-8':
        print(*objects, sep=sep, end=end, file=file)
    else:
        f = lambda obj: str(obj).encode(enc, errors='backslashreplace').decode(enc)
        print(*map(f, objects), sep=sep, end=end, file=file)

class YoutubeLiveStream:
  def __init__(self, channelId, channelName):
    self.channelId = channelId
    self.channelName = channelName
    self.liveVideoId = None
    self.name = channelName
    self.streamType = 'youtube'
  def updateLiveVideoId(self):
    if not self.liveVideoId:
      self.liveVideoId = YoutubeLiveStream.get_livestream(self.channelId, self.channelName)
  def viewers(ids):
    actual_ids = [id for id in ids if id]
    actual_ids_str = ','.join(actual_ids)
    youtube = YoutubeLiveStream.get_youtube()
    request = youtube.videos().list(
      part="liveStreamingDetails",
      id=actual_ids_str
    )
    response = request.execute()
    resultDict = {i['id']:YoutubeLiveStream.get_concurrent_viewers_from_item(i) for i in response['items'] if i.get('id')}
    # results = [resultDict[id] if resultDict.get(id) else None for id in ids]
    return resultDict

  def get_concurrent_viewers_from_item(i):
    if i:
      if i.get('liveStreamingDetails'):
        if i['liveStreamingDetails'].get('concurrentViewers'):
          return i['liveStreamingDetails']['concurrentViewers']
    return None

  def get_livestream(channelId, channelName):
    url = "https://www.youtube.com/channel/"+channelId+"/live"
    contents = urllib.request.urlopen(url).read().decode('utf-8')
    # uprint(contents)
    m = re.search('<link rel="canonical" href="https://www.youtube.com/watch\\?v=([^"]+)">',contents)
    # <link rel="canonical" href="https://www.youtube.com/watch?v=4FYZTFGoJVQ">
    # <link rel="canonical" href="https://www.youtube.com/channel/UCfpnY5NnBl-8L7SvICuYkYQ">
    if m:
      # print(m.groups()[0])
      return m.groups()[0]
    else:
      # print('no match')
      return None

  def get_google_credentials():
      """Shows basic usage of the Youtube v3 API.
      Prints the names and ids of the first 10 files the user has access to.
      """
      creds = None
      # The file token.json stores the user's access and refresh tokens, and is
      # created automatically when the authorization flow completes for the first
      # time.
      if os.path.exists('token.json'):
          creds = Credentials.from_authorized_user_file('token.json', SCOPES)
      # If there are no (valid) credentials available, let the user log in.
      if not creds or not creds.valid:
          if creds and creds.expired and creds.refresh_token:
              creds.refresh(Request())
          else:
              flow = InstalledAppFlow.from_client_secrets_file(
                  'credentials.json', SCOPES)
              creds = flow.run_local_server(port=0)
          # Save the credentials for the next run
          with open('token.json', 'w') as token:
              token.write(creds.to_json())
      return creds

  def get_youtube():
    creds = YoutubeLiveStream.get_google_credentials()
    youtube = build("youtube", "v3", credentials=creds)
    return youtube



class TwitchLiveStream:
  def __init__(self, channelId, channelName):
    self.channelId = channelId
    self.channelName = channelName
    self.liveVideoId = channelId.lower()
    self.name = channelName
    self.streamType = 'twitch'
  def updateLiveVideoId(self):
    pass
  def viewers(ids):
    actual_ids = [id for id in ids if id]
    data = TwitchLiveStream.get_data(actual_ids)
    return data

  def get_concurrent_viewers_from_item(i):
    if i:
      if i.get('liveStreamingDetails'):
        if i['liveStreamingDetails'].get('concurrentViewers'):
          return i['liveStreamingDetails']['concurrentViewers']
    return None

  clientId = '1l29z0y39ayqgt2loqjyekump3k0ff'
  clientSecret = 'uiz9c75yqeg03tr9izudbxbwrvg1hy'
  def get_access_token():
    url = 'https://id.twitch.tv/oauth2/token?client_id='+TwitchLiveStream.clientId+'&client_secret='+TwitchLiveStream.clientSecret+'&grant_type=client_credentials'
    response = requests.post(url)
    responseJson = response.text
    credentials = json.loads(responseJson)
    accessToken = credentials["access_token"]
    return accessToken

  def make_get_streams_url(logins):
    urlParams = ["user_login="+login for login in logins]
    url = 'https://api.twitch.tv/helix/streams?'+ '&'.join(urlParams)
    return url

  def get_data(ids):
    accessToken = TwitchLiveStream.get_access_token()
    headers = {'Authorization': 'Bearer '+accessToken, 'Client-Id': TwitchLiveStream.clientId }
    getStreamsUrl = TwitchLiveStream.make_get_streams_url(ids)
    response = requests.get(getStreamsUrl, headers=headers)
    streamsResponse = json.loads(response.text)
    streams = streamsResponse["data"]
    data = { stream['user_login']:str(stream['viewer_count']) for stream in streamsResponse['data']}
    return data


# evaluates one iteration
class StreamEvaluator:
  def __init__(self, streams,previousValues):
    self.streams = streams
    self.headings = [i.name for i in self.streams]
    self.previousValues = previousValues
    self.values = None
  def evaluate(self):
    for stream in self.streams:
      stream.updateLiveVideoId()
    videoIds = [s.liveVideoId for s in self.streams]
    youtubeVideoIds = [s.liveVideoId for s in self.streams if s.streamType == 'youtube']
    twitchVideoIds = [s.liveVideoId for s in self.streams if s.streamType == 'twitch']
    youtubeResultDict = YoutubeLiveStream.viewers(youtubeVideoIds)
    twitchResultDict = TwitchLiveStream.viewers(twitchVideoIds)
    resultsDict = youtubeResultDict | twitchResultDict
    self.values = [resultsDict[id] if resultsDict.get(id) else None for id in videoIds]
    return self.values
  def differences(self):
    if self.previousValues:
      diffs = [[h, pv, v] for h, pv, v in zip(self.headings, self.previousValues, self.values) if pv != v]
    else:
      diffs = [[h, None, v] for h, v in zip(self.headings, self.values)]
    return diffs
  def difference_strings(self):
    sl = ['***  ' + d[0] + ': ' + d[1] + ' -> ' + d[2] for d in self.differences()]
    return sl



def get_streams():
  with open('channels.json') as json_file:
    data = json.load(json_file)    
  streams = [YoutubeLiveStream(k,v) if k.startswith('UC') and len(k)==24 else TwitchLiveStream(k,v) for (k,v) in data.items()]
  return streams

def make_header(names):
    return 'timestamp,'+','.join(names)

def make_row(timestamp, values):
    x = ['' if v is None else v for v in values]
    return timestamp+','+','.join(x)

def append_log_file(txt):
    with open(logFilePath, "a") as f:
        f.write(txt+'\n')    

def append_change_log_file(txt):
    with open(changeLogFilePath, "a") as f:
        f.write(txt+'\n')    


streams = get_streams()
names = [s.name for s in streams]
append_log_file(make_header(names))
append_change_log_file(make_header(names))

previousValues = None
while True:
  ts = strftime("%Y-%m-%d %H:%M:%S", gmtime())
  print(ts)

  evaluator = StreamEvaluator(streams, previousValues)
  evaluator.evaluate()
  previousValues = evaluator.values
  
  append_log_file(make_row(ts, evaluator.values))

  diffs = evaluator.differences()

  if diffs:
    append_change_log_file(make_row(ts, evaluator.values))
    for [name, prev, curr] in diffs:
      print('***  ' + name + ': ' + str(prev) + ' -> ' + str(curr))

  time.sleep(sleepSeconds)


# https://stackoverflow.com/questions/66880585/how-to-scrape-music-charts-insights-page-from-charts-youtube-com
# INNERTUBE_API_KEY