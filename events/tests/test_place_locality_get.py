import pytest

from .utils import versioned_reverse as reverse


@pytest.mark.django_db
def test_get_localities(api_client, place, place2, place3, place4):
    place.address_locality_fi = "Turku"
    place.address_locality_sv = "Åbo"
    place.save()
    place2.address_locality_fi = "Kaarina"
    place2.address_locality_sv = "S:t Karins"
    place2.save()
    place3.address_locality_fi = "Raisio"
    place3.address_locality_sv = "Reso"
    place3.save()
    place4.address_locality_fi = "Raisio"
    place4.save()

    url = reverse('place_locality-list', version='v1')
    response = api_client.get(url, data=None, format='json')
    assert response.status_code == 200
    assert response.data["count"] == 3
    assert place.address_locality_fi in [entry["fi"] for entry in response.data["data"]]
    assert place2.address_locality_fi in [entry["fi"] for entry in response.data["data"]]
    assert place3.address_locality_fi in [entry["fi"] for entry in response.data["data"]]
