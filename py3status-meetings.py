import datetime
import os.path
import pickle
from dataclasses import dataclass
from operator import attrgetter
from typing import Union

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from pytz import timezone


class Duration:
    seconds: int

    def __init__(self, form: Union[int, datetime.timedelta]):
        if type(form) is int:
            self.seconds = form
        elif type(form) is datetime.timedelta:
            self.seconds = form.seconds
        else:
            raise TypeError("Expected int or timedelta")

    def minutes(self):
        return (self.seconds / 60) % 60

    def minutes_full(self):
        return self.seconds / 60

    def hours_full(self):
        return self.minutes_full() / 60

    def __str__(self):
        hours = '' if self.hours_full() < 1 else '%dh ' % self.hours_full()
        minutes = '%dm' % self.minutes()
        return f'{hours}{minutes}'


@dataclass
class Event:
    summary: str
    tz: datetime.tzinfo
    start: datetime
    end: datetime
    color: str

    def time_until(self) -> Duration:
        now = datetime.datetime.now(self.tz)
        return Duration(self.start - now)

    def to_string_next(self, precedingEvent):
        duration = Duration(self.end - self.start)
        duration_between = Duration(self.start - precedingEvent.end)
        return f'{duration_between} > {self.summary} ({duration})'


class GoogleCalendar:
    # If modifying these scopes, delete the file token.pickle.
    SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']

    def __init__(self):
        creds = None

        if os.path.exists('token.pickle'):
            with open('token.pickle', 'rb') as token:
                creds = pickle.load(token)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    '$HOME/.config/google/credentials.json', self.SCOPES)
                creds = flow.run_local_server(port=0)
            # Save the credentials for the next run
            with open('token.pickle', 'wb') as token:
                pickle.dump(creds, token)

        self._service = build('calendar', 'v3', credentials=creds)

    def get_next_events(self, calendar_names):
        events_result = self._service.calendarList().list().execute()
        raw_calendars = events_result.get('items', [])
        applicable_calendars = [cal for cal in raw_calendars if cal['summary'] in calendar_names]

        all_events = []
        for cal in applicable_calendars:
            all_events.extend([e for e in self._get_events(cal['id'], cal['backgroundColor'])])

        all_events.sort(key=attrgetter('start'))

        return all_events

    def _get_events(self, calendar_id, color) -> [Event]:
        now = datetime.datetime.utcnow()
        now_str = now.isoformat() + 'Z'  # 'Z' indicates UTC time
        top = datetime.datetime.utcnow() + datetime.timedelta(hours=24)
        events_result = self._service.events().list(calendarId=calendar_id, timeMin=now_str,
                                                    timeMax=top.isoformat() + 'Z',
                                                    maxResults=10, singleEvents=True,
                                                    orderBy='startTime').execute()
        events = events_result.get('items', [])

        parsed_events = []

        for event in events:
            if 'date' in event['start']:
                # All-day event, ignore
                continue

            tz = timezone(event['start']['timeZone']) if 'timezone' in event['start'] else timezone('utc')
            start_date = datetime.datetime.fromisoformat(event['start']['dateTime']).astimezone(tz)

            if start_date < datetime.datetime.now(tz):
                continue

            end_date = datetime.datetime.fromisoformat(event['end']['dateTime']).astimezone(tz)
            ev = Event(
                summary=event['summary'],
                tz=tz,
                start=start_date,
                end=end_date,
                color=color
            )
            parsed_events.append(ev)

        return parsed_events


def get_duration_color(time_until: Duration):
    if time_until.minutes_full() < 20:
        return '#FF0000'
    elif time_until.minutes_full() < 120:
        return '#FFFF00'
    else:
        return None


class Py3status:
    calendar = GoogleCalendar()
    calendar_names = []  # Put calendar names to track here

    def meetings(self):
        output = {'cached_until': self.py3.time_in(60)}

        all_events = self.calendar.get_next_events(self.calendar_names)

        next_event = all_events[0] if len(all_events) > 0 else None
        if next_event is not None:
            time_until = next_event.time_until()
            output['composite'] = [
                {
                    'full_text': f'In {time_until} ',
                    'color': get_duration_color(time_until)
                },
                {
                    'full_text': next_event.summary,
                    'color': next_event.color
                }
            ]
        else:
            output['full_text'] = 'No upcoming events'

        return output


if __name__ == "__main__":
    """
    Run module in test mode.
    """
    config = {
        'always_show': True,
    }
    from py3status.module_test import module_test

    module_test(Py3status, config=config)
