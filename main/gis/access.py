"""Who may open a village's map: that village's technical expert (role engineer) and admins."""
from main.access import can, role_of
from main.geography import norm


def village_of(user):
    """(CityVillage id or None, village name, county name) the user's profile belongs to."""
    profile = user.profile
    return (profile.city_village_fk_id, profile.city_village_name or profile.city_village, profile.county)


def may_use(user, village_map, action='gis.view'):
    """True if ``user`` may use ``village_map``: the role is allowed AND the profile is in that village.

    Admins skip the village check. The match is by the divisions table when the profile is linked to it, else
    by name, and the county must agree whenever the profile has one, so another county's village that shares
    the name is not let in.
    """
    if not can(user, action):
        return False
    if user.is_superuser or role_of(user) == 'admin':
        return True
    link, name, county = village_of(user)
    if link and village_map.city_village_id:
        return link == village_map.city_village_id
    if norm(name) != norm(village_map.name):
        return False
    return not (county and village_map.county_name and norm(county) != norm(village_map.county_name))


def maps_for(user):
    """The village maps ``user`` may open (admins: all of them)."""
    from main.models import VillageMap
    if not user.is_authenticated or not can(user, 'gis.view'):
        return []
    return [m for m in VillageMap.objects.all() if may_use(user, m)]
