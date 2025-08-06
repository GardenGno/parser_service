from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import Request
from .serializers import RequestSerializer
import threading
import asyncio

def run_async_task(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(coro)
    loop.close()

class StartParseView(APIView):
    def post(self, request):
        serializer = RequestSerializer(data=request.data)
        if serializer.is_valid():
            parse_request = serializer.save(status='pending')
            from .tasks import run_parser_task
            # ВАЖНО: просто передаём функцию и аргумент, без run_async_task!
            threading.Thread(target=run_parser_task, args=(parse_request.id,)).start()
            return Response({'request_id': parse_request.id}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ParseStatusView(APIView):
    """
    GET-запрос для получения только статуса по id запроса.
    """
    def get(self, request, pk):
        try:
            parse_request = Request.objects.get(pk=pk)
        except Request.DoesNotExist:
            return Response({'error': 'Not found'}, status=404)
        return Response({'status': parse_request.status})