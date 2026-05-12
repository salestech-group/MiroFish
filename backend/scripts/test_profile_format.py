"""Profile-format generation tests for OASIS compatibility.

Verifies that:
1. Twitter profiles serialize to CSV format.
2. Reddit profiles serialize to detailed JSON format.
"""

import os
import sys
import json
import csv
import tempfile

# Add the project root to sys.path so the ``app`` package resolves.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Bind t / set_locale at module top-level. Stubs are used if the locale
# package is not on the import path (R3.AC5 graceful degradation).
try:
    from app.utils.locale import t, set_locale
except ImportError:
    def t(key, **kwargs):
        return key

    def set_locale(_):
        pass

from app.services.oasis_profile_generator import OasisProfileGenerator, OasisAgentProfile


def test_profile_formats():
    """Exercise both profile-format outputs end-to-end."""
    print("=" * 60)
    print(t("scripts.test_profile_format.header_main"))
    print("=" * 60)

    # Build a small set of test profiles.
    test_profiles = [
        OasisAgentProfile(
            user_id=0,
            user_name="test_user_123",
            name="Test User",
            bio="A test user for validation",
            persona="Test User is an enthusiastic participant in social discussions.",
            karma=1500,
            friend_count=100,
            follower_count=200,
            statuses_count=500,
            age=25,
            gender="male",
            mbti="INTJ",
            country="China",
            profession="Student",
            interested_topics=["Technology", "Education"],
            source_entity_uuid="test-uuid-123",
            source_entity_type="Student",
        ),
        OasisAgentProfile(
            user_id=1,
            user_name="org_official_456",
            name="Official Organization",
            bio="Official account for Organization",
            persona="This is an official institutional account that communicates official positions.",
            karma=5000,
            friend_count=50,
            follower_count=10000,
            statuses_count=200,
            profession="Organization",
            interested_topics=["Public Policy", "Announcements"],
            source_entity_uuid="test-uuid-456",
            source_entity_type="University",
        ),
    ]
    
    generator = OasisProfileGenerator.__new__(OasisProfileGenerator)

    # Use a temp directory for the test fixtures.
    with tempfile.TemporaryDirectory() as temp_dir:
        twitter_path = os.path.join(temp_dir, "twitter_profiles.csv")
        reddit_path = os.path.join(temp_dir, "reddit_profiles.json")

        # Twitter CSV format.
        print("\n" + t("scripts.test_profile_format.header_twitter"))
        print("-" * 40)
        generator._save_twitter_csv(test_profiles, twitter_path)

        # Read back and verify the CSV.
        with open(twitter_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        print(t("scripts.test_profile_format.file", path=twitter_path))
        print(t("scripts.test_profile_format.rows", count=len(rows)))
        print(t("scripts.test_profile_format.headers", headers=list(rows[0].keys())))
        print(t("scripts.test_profile_format.sample_data_row"))
        for key, value in rows[0].items():
            print(t("scripts.test_profile_format.sample_kv", key=key, value=value))

        # Verify the required fields are present.
        required_twitter_fields = ['user_id', 'user_name', 'name', 'bio',
                                   'friend_count', 'follower_count', 'statuses_count', 'created_at']
        missing = set(required_twitter_fields) - set(rows[0].keys())
        if missing:
            print(t("scripts.test_profile_format.error_missing_fields", fields=missing))
        else:
            print(t("scripts.test_profile_format.pass_all_fields"))

        # Reddit JSON format.
        print("\n" + t("scripts.test_profile_format.header_reddit"))
        print("-" * 40)
        generator._save_reddit_json(test_profiles, reddit_path)

        # Read back and verify the JSON.
        with open(reddit_path, 'r', encoding='utf-8') as f:
            reddit_data = json.load(f)

        print(t("scripts.test_profile_format.file", path=reddit_path))
        print(t("scripts.test_profile_format.entries", count=len(reddit_data)))
        print(t("scripts.test_profile_format.fields", fields=list(reddit_data[0].keys())))
        print(t("scripts.test_profile_format.sample_data_entry"))
        print(json.dumps(reddit_data[0], ensure_ascii=False, indent=4))

        # Verify the detailed Reddit format fields.
        required_reddit_fields = ['realname', 'username', 'bio', 'persona']
        optional_reddit_fields = ['age', 'gender', 'mbti', 'country', 'profession', 'interested_topics']

        missing = set(required_reddit_fields) - set(reddit_data[0].keys())
        if missing:
            print(t("scripts.test_profile_format.error_missing_required", fields=missing))
        else:
            print(t("scripts.test_profile_format.pass_all_fields"))

        present_optional = set(optional_reddit_fields) & set(reddit_data[0].keys())
        print(t("scripts.test_profile_format.info_optional", fields=present_optional))

    print("\n" + "=" * 60)
    print(t("scripts.test_profile_format.footer_done"))
    print("=" * 60)


def show_expected_formats():
    """Print the canonical OASIS-expected profile formats for reference."""
    print("\n" + "=" * 60)
    print(t("scripts.test_profile_format.ref_header_main"))
    print("=" * 60)

    print("\n" + t("scripts.test_profile_format.ref_header_twitter"))
    print("-" * 40)
    twitter_example = """user_id,user_name,name,bio,friend_count,follower_count,statuses_count,created_at
0,user0,User Zero,I am user zero with interests in technology.,100,150,500,2023-01-01
1,user1,User One,Tech enthusiast and coffee lover.,200,250,1000,2023-01-02"""
    print(twitter_example)

    print("\n" + t("scripts.test_profile_format.ref_header_reddit"))
    print("-" * 40)
    reddit_example = [
        {
            "realname": "James Miller",
            "username": "millerhospitality",
            "bio": "Passionate about hospitality & tourism.",
            "persona": "James is a seasoned professional in the Hospitality & Tourism industry...",
            "age": 40,
            "gender": "male",
            "mbti": "ESTJ",
            "country": "UK",
            "profession": "Hospitality & Tourism",
            "interested_topics": ["Economics", "Business"]
        }
    ]
    print(json.dumps(reddit_example, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    set_locale(os.environ.get("MIROFISH_LOCALE", "zh"))
    test_profile_formats()
    show_expected_formats()


