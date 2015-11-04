import boto3
from django.conf import settings
from celery.contrib.methods import task
from mover.models import MoveRequest


class CeleryBackend(object):
    def __init__(self, from_, to):
        self.move_from = from_
        self.move_to = to

    @task
    def _move_file(self, filename):
        s3 = boto3.client('s3', aws_access_key_id=settings.AWS_KEY, aws_secret_access_key=settings.AWS_SECRET)
        if MoveRequest.objects.filter(filename=filename, status=MoveRequest.STATUS_RUNNING).count():
            print("There is already a running task for the  file %s" % filename)
            return True

        request = MoveRequest.objects.filter(filename=filename, status__in=[MoveRequest.STATUS_ERROR, MoveRequest.STATUS_QUEUED]).first()
        if not request:
            request = MoveRequest(filename=filename)
        request.status = MoveRequest.STATUS_RUNNING
        request.save()
        try:
            s3.copy_object(Key=filename, Bucket=self.move_to, CopySource="%s/%s" % (self.move_from, filename))
            s3.delete_object(Bucket=self.move_from, Key=filename)
            request.status = MoveRequest.STATUS_COMPLETED
            request.save()
        except Exception as e:
            print(e)
            request.status = MoveRequest.STATUS_ERROR
            request.save()
            return False
        return True

    @task
    def _create_sample_file(self, filename, content):
        s3 = boto3.client('s3', aws_access_key_id=settings.AWS_KEY, aws_secret_access_key=settings.AWS_SECRET)
        return s3.put_object(Bucket=self.move_from, Body=content, Key=filename)

    def move_files(self, filenames):
        for fname in filenames:
            self._move_file.delay(fname)
            print('File move requested for file %s' % fname)

    def restart_failed(self):
        files = list(MoveRequest.objects.filter(status=MoveRequest.STATUS_ERROR).values_list('filename', flat=True))
        return self.move_files(files)

    def create_sample_files(self, filenames, content):
        for fname in filenames:
            self._create_sample_file.delay(fname, content)
            print(fname)