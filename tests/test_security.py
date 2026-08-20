import unittest
from aurea.security import password_hash,password_matches,password_errors,code_hash

class SecurityTests(unittest.TestCase):
    def test_password_roundtrip(self):
        h=password_hash('SenhaForte123')
        self.assertTrue(password_matches(h,'SenhaForte123'))
        self.assertFalse(password_matches(h,'SenhaErrada123'))
        self.assertNotIn('SenhaForte123',h)

    def test_password_rules(self):
        self.assertTrue(password_errors('curta'))
        self.assertFalse(password_errors('SenhaForte123'))

    def test_code_hash_is_keyed(self):
        self.assertEqual(code_hash('s','123456'),code_hash('s','123456'))
        self.assertNotEqual(code_hash('s','123456'),code_hash('x','123456'))

if __name__=='__main__':unittest.main()
