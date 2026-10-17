"""Role groups used across the app (profile ``role`` values). No imports, so models, forms and views can all use it.

``main/access.py`` maps *actions* to roles; these are the plain groups that several places need.
"""
CITIZEN_ROLES = ('citizen', 'owner', 'resident')                                     # verified automatically on sign-up
MUNICIPAL_STAFF_ROLES = ('dehyari', 'engineer', 'inspector', 'accountant', 'council')
ADMIN_ROLES = ('admin',)
ALL_STAFF_ROLES = MUNICIPAL_STAFF_ROLES + ADMIN_ROLES
