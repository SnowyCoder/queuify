
from datetime import datetime, timedelta
from uuid import uuid4
from django.db import connection
from django.http import Http404, HttpRequest, JsonResponse
from django.shortcuts import render, get_object_or_404
from .models import QQueue, QueueUserRole


def queue_stats(request: HttpRequest, pk: uuid4):
    queue = get_object_or_404(QQueue, id=pk)

    user_role = queue.get_user_role(request.user)
    if not request.user.has_perm('queues.view_all_stats') and  user_role not in [QueueUserRole.OWNER, QueueUserRole.EMPLOYEE]:
        raise Http404()

    return render(request, 'queues/stats.html', context={
        'queue': queue,
    })


def api_query(request: HttpRequest, pk: uuid4):
    queue = get_object_or_404(QQueue, id=pk)

    user_role = queue.get_user_role(request.user)
    if not request.user.has_perm('queues.view_all_stats') and  user_role not in [QueueUserRole.OWNER, QueueUserRole.EMPLOYEE]:
        raise Http404()

    # Input: { from, to }
    # { nameFormat, tickets: { x, ticket, canceledQueue, canceledUser }, waits: { x, avgWait } }
    datefmt = '%Y-%m-%d'

    start = datetime.strptime(request.GET.get('from'), datefmt)
    end = datetime.strptime(request.GET.get('to'), datefmt)

    query = f'''
SELECT date(requested_time) as name,
count(CASE WHEN state = "SER" THEN 1 END) as served,
count(CASE WHEN state = "QCA" THEN 1 END) as canceledQueue,
count(CASE WHEN state = "UCA" THEN 1 END) as canceledUser,
count(CASE WHEN state = "OPE" THEN 1 END) as open,
-- Non-served tickets have NULL wait_time_secs
avg(wait_time_secs) as avgWait
FROM queues_ticket
WHERE queue_id = %s AND date(requested_time) BETWEEN %s AND %s
GROUP BY name
'''
    args = (
        pk.hex,
        start.strftime(datefmt),
        end.strftime(datefmt)
    )
    AGGREG_NAMES = {
        'tickets': ('served', 'canceledQueue', 'canceledUser', 'open'),
        'waits': ('avgWait',)
    }
    data = {
        'nameFormat': datefmt,
    }
    data.update(
        {aggName: [[name] for name in (('x',) + names)] for aggName, names in AGGREG_NAMES.items()}
    )
    with connection.cursor() as cursor:
        cursor.execute(query, args)
        res = cursor.fetchall()
        old_date = -1

        def fill_gaps_until(idate):
            nonlocal old_date
            for i in range(old_date + 1, idate):
                datestr = (start + timedelta(days=i)).strftime(datefmt)

                for aggName, names in AGGREG_NAMES.items():
                    data[aggName][0].append(datestr)
                    for i in range(0, len(names)):
                        data[aggName][i + 1].append(0)

            old_date = idate


        for row in res:
            idate = (datetime.strptime(row[0], datefmt) - start).days
            # Fill gaps
            fill_gaps_until(idate)

            i = 1
            for aggName, keys in AGGREG_NAMES.items():
                data[aggName][0].append(row[0])
                for ikey in range(len(keys)):
                    data[aggName][ikey + 1].append(row[i] if row[i] is not None else 0)
                    i += 1
        fill_gaps_until((end - start).days + 1)

    regions = []
    last_start = None
    def push_end():
        nonlocal last_start
        regions.append({
            'start': (last_start - timedelta(days=1)).date().strftime(datefmt)  + 'T12:00',
            'end': (day - timedelta(days=1)).date().strftime(datefmt) + 'T12:00',
        })

        last_start = None

    for i in range(0, (end - start).days + 2):
        day = (start + timedelta(days=i))
        is_closed = queue.get_open_range(day) is None
        if is_closed and last_start is None: # Open
            last_start = day
        elif not is_closed and  last_start is not None: # Close
            push_end()

    if last_start is not None:
        push_end()

    data['regions'] = regions


    return JsonResponse(data)
