import hashlib

from django.shortcuts import render
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_POST

from .models import Event, Registration


def index(req):
    if settings.DEBUG:
        template = 'magnovite/events.html'
    else:
        template = 'magnovite/dist/events.html'

    events = Event.objects.all()

    return render(req, template, {
        'events': events
    })


def details(req, slug):
    event = get_object_or_404(Event, slug=slug)

    is_registered = False
    if req.user.is_authenticated():
        is_registered = req.user.profile.is_registered_to_event(event)

    heads = event.heads.all()
    head_one = None
    head_two = None
    if len(heads) == 1:
        head_one = heads[0]
    elif len(heads) >= 2:
        head_one = heads[0]
        head_two = heads[1]
        # we will show only two event heads

    team_profiles = []
    team_id = ''
    team_owner = False
    if is_registered and event.is_multiple():
        reg_obj = Registration.objects.get(event=event, profile=req.user.profile)
        team_id = reg_obj.team_id
        team_owner = reg_obj.is_owner
        team_profiles = [x.profile for x in Registration.objects.filter(team_id=team_id)]

        # add dummy profiles so the list has empty placeholders
        for _ in range(event.team_max - len(team_profiles)):
            team_profiles.append({'name': '<empty>'})

    # analytics
    event.views += 1
    event.save()

    if settings.DEBUG:
        template = 'magnovite/eventDetails.html'
    else:
        template = 'magnovite/dist/eventDetails.html'

    return render(req, template, {
        'event': event,
        'is_registered': is_registered,
        'head_one': head_one,
        'head_two': head_two,
        'team_profiles': team_profiles,
        'team_id': team_id,
        'team_owner': team_owner
    })


@require_POST
def register(req, id, team_id=None):
    if not req.user.is_authenticated():
        return JsonResponse({
            'errorCode': 'login',
            'errorMessage': 'Please login first'
        }, status=400)

    if not req.user.is_staff:
        return JsonResponse({
            'errorCode': 'unauthorized',
            'errorMessage': 'Sorry, Our registrations are not open yet, pleaes check back on 1st of Feb'
        }, status=400)

    # you can only register if profile is complete
    if not req.user.profile.is_complete():
        return JsonResponse({
            'errorCode': 'profile_incomplete',
            'actionType': 'redirect',
            'actionText': 'Complete Now',
            'redirectLocation': '/profile/',
            'errorMessage': 'You need to complete your profile first'
        }, status=400)


    event = get_object_or_404(Event, id=id)

    # you cannot register if you are on the blank pack
    if event.is_individual() and req.user.profile.pack == 'none':
        return JsonResponse({
            'errorCode': 'no_pack',
            'actionType': 'redirect',
            'actionText': 'View Pack',
            'redirectLocation': '/profile/#pack',
            'errorMessage': 'You need to opt-in for a pack before registering. Follow the link below'
        }, status=400)

    if (event.is_individual() and
        req.user.profile.pack == 'single' and
        req.user.profile.registered_events.filter(team_type__ne='group').count() == 1):
        return JsonResponse({
            'errorCode': 'pack_full',
            'actionType': 'redirect',
            'actionText': 'Upgrade Pack',
            'redirectLocation': '/profile/#pack',
            'errorMessage': 'You have opted for Single Pack. You can only register to one individual event.'
        }, status=400)

    r = Registration()
    r.event = event
    r.profile = req.user.profile

    if event.is_multiple():
        # team registrations
        # If team id is not given, a new create will be crated for this
        # user/event combo and the user will be registered in that team
        if team_id == None:
            corpus = req.user.email + event.slug + settings.SECRET_KEY[:10]
            team_id = hashlib.sha1(corpus.encode('utf-8')).hexdigest()[:5]
        else:
            # make sure team_id is valid, if user has given a team_id
            # then if it is valid, it must be in our registration table

            num = Registration.objects.filter(team_id=team_id).count()

            if num == 0:
                return HttpResponse(status=404)

            # make sure this team is not full
            if num == event.team_max:
                return JsonResponse({
                    'errorCode': 'team_full',
                    'errorMessage': 'The team is full!'
                })

        r.team_id = team_id

    try:
        r.save()
    except Exception:
        return JsonResponse({
            'errorCode': 'unknown',
            'errorMessage': 'Something went wrong! Try refreshing the page, or try again later'
        }, status=400)

    # success
    event.registrations += 1
    event.save()

    if event.is_multiple():
        registrations = Registration.objects.filter(team_id=team_id)
        names = [r.profile for r in registrations]

        def fn(val):
            out = {}
            if val == req.user.profile:
                out['me'] = True

            out['name'] = val.name
            return out

        names = [_ for _ in map(fn, names)]

        # add <empty> as placeholders
        for _ in range(event.team_max - len(names)):
            names.append({'name': '&ltempty&gt'})

        return JsonResponse({
            'teamId': team_id,
            'members': names
        })

    return HttpResponse(status=200)


@require_POST
def unregister(req, id):
    if not req.user.is_authenticated():
        return HttpResponse(status=400)

    event = get_object_or_404(Event, id=id)

    try:
        reg = Registration.objects.get(event=event, profile=req.user.profile)
        reg.delete()

        event.registrations -= 1
        event.save()
    except Registration.DoesNotExist:
        pass

    # we return 200, even if the user was previously
    # not registered to the event
    return HttpResponse(status=200)



