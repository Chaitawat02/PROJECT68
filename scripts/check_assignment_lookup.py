#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myproject.settings')
django.setup()

from main.models import SpeakerAssignment

def check(aid: str):
    print('Checking assignment_id:', aid)
    qs = SpeakerAssignment.objects.filter(assignment_id=aid)
    print('Found by assignment_id:', qs.exists(), 'Count:', qs.count())
    if qs.exists():
        obj = qs.first()
        print('PK:', obj.pk, 'assignment_id:', getattr(obj, 'assignment_id', None), 'speaker:', getattr(getattr(obj, 'speaker', None), 'user', None))
    else:
        try:
            pk = int(aid)
            obj = SpeakerAssignment.objects.get(pk=pk)
            print('Found by PK:', obj.pk)
        except Exception as e:
            print('Not found by PK or assignment_id. Error:', repr(e))

if __name__ == '__main__':
    check('0753009317977')
