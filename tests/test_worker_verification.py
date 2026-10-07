import io
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import verify_worker

class WorkerVerificationTests(unittest.TestCase):
    def test_only_explicit_country_denial_can_switch_to_authenticated_verification(self):
        denied = urllib.error.HTTPError('https://example.com', 403, 'Forbidden', {}, io.BytesIO(b'{"error":"country_not_allowed"}'))
        with patch('urllib.request.urlopen', side_effect=denied):
            with self.assertRaises(verify_worker.CountryBlocked):
                verify_worker.fetch_public('/health')
        for status, body in [(403, b'{"error":"other"}'), (503, b'{"error":"country_not_allowed"}'), (403, b'not json')]:
            error = urllib.error.HTTPError('https://example.com', status, 'Error', {}, io.BytesIO(body))
            with patch('urllib.request.urlopen', side_effect=error):
                with self.assertRaises(urllib.error.HTTPError):
                    verify_worker.fetch_public('/health')

    def test_country_denial_still_requires_successful_authenticated_database_check(self):
        with patch.object(verify_worker, 'fetch_public', side_effect=verify_worker.CountryBlocked()), patch.object(verify_worker, 'verify_private', side_effect=RuntimeError('database failed')) as private:
            with self.assertRaises(RuntimeError):
                verify_worker.verify('colowide')
            private.assert_called_once_with('colowide')

    def test_arbitrary_issuer_cannot_be_interpolated_into_sql(self):
        with patch.object(verify_worker, 'query_d1') as query:
            with self.assertRaises(ValueError):
                verify_worker.verify_private("x'; DROP TABLE stores;--")
            query.assert_not_called()

    def test_private_health_does_not_accept_empty_database(self):
        with patch.object(verify_worker, 'query_d1', return_value=[{'geo_count':0,'reference_count':1}]):
            with self.assertRaises(RuntimeError):
                verify_worker.verify_private()

if __name__ == '__main__':
    unittest.main()
