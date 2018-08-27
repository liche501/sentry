from __future__ import absolute_import

import responses

from six.moves.urllib.parse import urlparse, urlencode, parse_qs

from sentry.integrations.vsts import VstsIntegrationProvider
from sentry.testutils import IntegrationTestCase


class VstsIntegrationTestCase(IntegrationTestCase):
    provider = VstsIntegrationProvider

    def setUp(self):
        super(VstsIntegrationTestCase, self).setUp()

        self.access_token = '9d646e20-7a62-4bcc-abc0-cb2d4d075e36'
        self.refresh_token = '32004633-a3c0-4616-9aa0-a40632adac77'

        self.vsts_account_id = 'c8a585ae-b61f-4ba6-833c-9e8d5d1674d8'
        self.vsts_account_name = 'MyVSTSAccount'
        self.vsts_account_uri = 'https://MyVSTSAccount.vssps.visualstudio.com:443/'

        self.vsts_user_id = 'd6245f20-2af8-44f4-9451-8107cb2767db'
        self.vsts_user_name = 'Foo Bar'
        self.vsts_user_email = 'foobar@example.com'

        self.repo_id = '47166099-3e16-4868-9137-22ac6b05b06e'
        self.repo_name = 'cool-service'

        self.project_a = {
            'id': 'eb6e4656-77fc-42a1-9181-4c6d8e9da5d1',
            'name': 'ProjectA',
        }

        self.project_b = {
            'id': '6ce954b1-ce1f-45d1-b94d-e6bf2464ba2c',
            'name': 'ProjectB',
        }

        responses.start()
        self._stub_vsts()

    def tearDown(self):
        responses.stop()

    def _stub_vsts(self):
        responses.reset()

        responses.add(
            responses.POST,
            'https://app.vssps.visualstudio.com/oauth2/token',
            json={
                'access_token': self.access_token,
                'token_type': 'grant',
                'expires_in': 300,  # seconds (5 min)
                'refresh_token': self.refresh_token,
            },
        )

        responses.add(
            responses.GET,
            'https://app.vssps.visualstudio.com/_apis/accounts',
            json=[{
                'AccountId': self.vsts_account_id,
                'AccountUri': self.vsts_account_uri,
                'AccountName': self.vsts_account_name,
                'Properties': {},
            }],
        )

        responses.add(
            responses.GET,
            'https://app.vssps.visualstudio.com/_apis/profile/profiles/me?api-version=1.0',
            json={
                'id': self.vsts_user_id,
                'displayName': self.vsts_user_name,
                'emailAddress': self.vsts_user_email,
            },
        )

        responses.add(
            responses.GET,
            'https://app.vssps.visualstudio.com/_apis/connectionData/',
            json={
                'authenticatedUser': {
                    'subjectDescriptor': self.vsts_account_id,
                },
            },
        )

        responses.add(
            responses.GET,
            'https://{}.visualstudio.com/DefaultCollection/_apis/projects'.format(
                self.vsts_account_name.lower(),
            ),
            json={
                'value': [
                    self.project_a,
                    self.project_b,
                ],
            },
        )

        responses.add(
            responses.POST,
            'https://{}.visualstudio.com/_apis/hooks/subscriptions'.format(
                self.vsts_account_name.lower(),
            ),
            json=CREATE_SUBSCRIPTION,
        )

        responses.add(
            responses.GET,
            'https://{}.visualstudio.com/_apis/git/repositories'.format(
                self.vsts_account_name.lower(),
            ),
            json={
                'value': [{
                    'id': self.repo_id,
                    'name': self.repo_name,
                    'project': {
                        'name': self.project_a['name'],
                    },
                }],
            },
        )

        responses.add(
            responses.GET,
            'https://{}.visualstudio.com/{}/_apis/wit/workitemtypes/{}/states'.format(
                self.vsts_account_name.lower(),
                self.project_a['name'],
                'Bug',
            ),
            json={
                'value': [{'name': 'resolve_status'},
                          {'name': 'resolve_when'},
                          {'name': 'regression_status'},
                          {'name': 'sync_comments'},
                          {'name': 'sync_forward_assignment'},
                          {'name': 'sync_reverse_assignment'}],
            }
        )

    def assert_installation(self):
        # Initial request to the installation URL for VSTS
        resp = self.client.get(self.init_path)

        redirect = urlparse(resp['Location'])
        query = parse_qs(redirect.query)

        assert resp.status_code == 302
        assert redirect.scheme == 'https'
        assert redirect.netloc == 'app.vssps.visualstudio.com'
        assert redirect.path == '/oauth2/authorize'

        # OAuth redirect back to Sentry (identity_pipeline_view)
        resp = self.client.get('{}?{}'.format(
            self.setup_path,
            urlencode({
                'code': 'oauth-code',
                'state': query['state'][0],
            }),
        ))

        assert resp.status_code == 200
        assert '<option value="{}"'.format(self.vsts_account_id) in resp.content

        # User choosing which VSTS Account to use (AccountConfigView)
        # Final step.
        return self.client.post(
            self.setup_path,
            {
                'account': self.vsts_account_id,
                'provider': 'vsts',
            },
        )


COMPARE_COMMITS_EXAMPLE = b"""
{
  "count": 1,
  "value": [
    {
      "commitId": "6c36052c58bde5e57040ebe6bdb9f6a52c906fff",
      "author": {
        "name": "max bittker",
        "email": "max@sentry.io",
        "date": "2018-04-24T00:03:18Z"
      },
      "committer": {
        "name": "max bittker",
        "email": "max@sentry.io",
        "date": "2018-04-24T00:03:18Z"
      },
      "comment": "Updated README.md",
      "changeCounts": {"Add": 0, "Edit": 1, "Delete": 0},
      "url":
        "https://mbittker.visualstudio.com/_apis/git/repositories/b1e25999-c080-4ea1-8c61-597c4ec41f06/commits/6c36052c58bde5e57040ebe6bdb9f6a52c906fff",
      "remoteUrl":
        "https://mbittker.visualstudio.com/_git/MyFirstProject/commit/6c36052c58bde5e57040ebe6bdb9f6a52c906fff"
    }
  ]
}
"""


FILE_CHANGES_EXAMPLE = b"""
{
  "changeCounts": {"Edit": 1},
  "changes": [
    {
      "item": {
        "objectId": "b48e843656a0a12926a0bcedefe8ef3710fe2867",
        "originalObjectId": "270b590a4edf3f19aa7acc7b57379729e34fc681",
        "gitObjectType": "blob",
        "commitId": "6c36052c58bde5e57040ebe6bdb9f6a52c906fff",
        "path": "/README.md",
        "url":
          "https://mbittker.visualstudio.com/DefaultCollection/_apis/git/repositories/b1e25999-c080-4ea1-8c61-597c4ec41f06/items/README.md?versionType=Commit&version=6c36052c58bde5e57040ebe6bdb9f6a52c906fff"
      },
      "changeType": "edit"
    }
  ]
}
"""
WORK_ITEM_RESPONSE = """{
  "id": 309,
  "rev": 1,
  "fields": {
    "System.AreaPath": "Fabrikam-Fiber-Git",
    "System.TeamProject": "Fabrikam-Fiber-Git",
    "System.IterationPath": "Fabrikam-Fiber-Git",
    "System.WorkItemType": "Product Backlog Item",
    "System.State": "New",
    "System.Reason": "New backlog item",
    "System.CreatedDate": "2015-01-07T18:13:01.807Z",
    "System.CreatedBy": "Jamal Hartnett <fabrikamfiber4@hotmail.com>",
    "System.ChangedDate": "2015-01-07T18:13:01.807Z",
    "System.ChangedBy": "Jamal Hartnett <fabrikamfiber4@hotmail.com>",
    "System.Title": "Hello",
    "Microsoft.VSTS.Scheduling.Effort": 8,
    "WEF_6CB513B6E70E43499D9FC94E5BBFB784_Kanban.Column": "New",
    "System.Description": "Fix this."
  },
  "_links": {
    "self": {
      "href": "https://fabrikam-fiber-inc.visualstudio.com/DefaultCollection/_apis/wit/workItems/309"
    },
    "workItemUpdates": {
      "href": "https://fabrikam-fiber-inc.visualstudio.com/DefaultCollection/_apis/wit/workItems/309/updates"
    },
    "workItemRevisions": {
      "href": "https://fabrikam-fiber-inc.visualstudio.com/DefaultCollection/_apis/wit/workItems/309/revisions"
    },
    "workItemHistory": {
      "href": "https://fabrikam-fiber-inc.visualstudio.com/DefaultCollection/_apis/wit/workItems/309/history"
    },
    "html": {
      "href": "https://fabrikam-fiber-inc.visualstudio.com/web/wi.aspx?pcguid=d81542e4-cdfa-4333-b082-1ae2d6c3ad16&id=309"
    },
    "workItemType": {
      "href": "https://fabrikam-fiber-inc.visualstudio.com/DefaultCollection/6ce954b1-ce1f-45d1-b94d-e6bf2464ba2c/_apis/wit/workItemTypes/Product%20Backlog%20Item"
    },
    "fields": {
      "href": "https://fabrikam-fiber-inc.visualstudio.com/DefaultCollection/_apis/wit/fields"
    }
  },
  "url": "https://fabrikam-fiber-inc.visualstudio.com/DefaultCollection/_apis/wit/workItems/309"
}"""

GET_USERS_RESPONSE = b"""{
  "count": 4,
  "value": [
    {
      "subjectKind": "user",
      "cuid": "ec09a4d8-d914-4f28-9e39-23d52b683f90",
      "domain": "Build",
      "principalName": "51ac8d19-6694-459f-a65e-bec30e9e2e33",
      "mailAddress": "",
      "origin": "vsts",
      "originId": "ec09a4d8-d914-4f28-9e39-23d52b683f90",
      "displayName": "Project Collection Build Service (Ftottentest2)",
      "_links": {
        "self": {
          "href": "https://fabrikam.vssps.visualstudio.com/_apis/graph/users/TWljcm9zb2Z0LlRlYW1Gb3VuZGF0aW9uLlNlcnZpY2VJZGVudGl0eTtmMzViOTAxNS1jZGU4LTQ4MzQtYTFkNS0wOWU4ZjM1OWNiODU6QnVpbGQ6NTFhYzhkMTktNjY5NC00NTlmLWE2NWUtYmVjMzBlOWUyZTMz"
        },
        "memberships": {
          "href": "https://fabrikam.vssps.visualstudio.com/_apis/graph/memberships/TWljcm9zb2Z0LlRlYW1Gb3VuZGF0aW9uLlNlcnZpY2VJZGVudGl0eTtmMzViOTAxNS1jZGU4LTQ4MzQtYTFkNS0wOWU4ZjM1OWNiODU6QnVpbGQ6NTFhYzhkMTktNjY5NC00NTlmLWE2NWUtYmVjMzBlOWUyZTMz"
        }
      },
      "url": "https://fabrikam.vssps.visualstudio.com/_apis/graph/users/TWljcm9zb2Z0LlRlYW1Gb3VuZGF0aW9uLlNlcnZpY2VJZGVudGl0eTtmMzViOTAxNS1jZGU4LTQ4MzQtYTFkNS0wOWU4ZjM1OWNiODU6QnVpbGQ6NTFhYzhkMTktNjY5NC00NTlmLWE2NWUtYmVjMzBlOWUyZTMz",
      "descriptor": "TWljcm9zb2Z0LlRlYW1Gb3VuZGF0aW9uLlNlcnZpY2VJZGVudGl0eTtmMzViOTAxNS1jZGU4LTQ4MzQtYTFkNS0wOWU4ZjM1OWNiODU6QnVpbGQ6NTFhYzhkMTktNjY5NC00NTlmLWE2NWUtYmVjMzBlOWUyZTMz"
    },
    {
      "subjectKind": "user",
      "metaType": "member",
      "cuid": "00ca946b-2fe9-4f2a-ae2f-40d5c48001bc",
      "domain": "LOCAL AUTHORITY",
      "principalName": "TeamFoundationService (TEAM FOUNDATION)",
      "mailAddress": "",
      "origin": "vsts",
      "originId": "00ca946b-2fe9-4f2a-ae2f-40d5c48001bc",
      "displayName": "TeamFoundationService (TEAM FOUNDATION)",
      "_links": {
        "self": {
          "href": "https://fabrikam.vssps.visualstudio.com/_apis/graph/users/TWljcm9zb2Z0LklkZW50aXR5TW9kZWwuQ2xhaW1zLkNsYWltc0lkZW50aXR5Ozc3ODlmMDlkLWUwNTMtNGYyZS1iZGVlLTBjOGY4NDc2YTRiYw"
        },
        "memberships": {
          "href": "https://fabrikam.vssps.visualstudio.com/_apis/graph/memberships/TWljcm9zb2Z0LklkZW50aXR5TW9kZWwuQ2xhaW1zLkNsYWltc0lkZW50aXR5Ozc3ODlmMDlkLWUwNTMtNGYyZS1iZGVlLTBjOGY4NDc2YTRiYw"
        }
      },
      "url": "https://fabrikam.vssps.visualstudio.com/_apis/graph/users/TWljcm9zb2Z0LklkZW50aXR5TW9kZWwuQ2xhaW1zLkNsYWltc0lkZW50aXR5Ozc3ODlmMDlkLWUwNTMtNGYyZS1iZGVlLTBjOGY4NDc2YTRiYw",
      "descriptor": "TWljcm9zb2Z0LklkZW50aXR5TW9kZWwuQ2xhaW1zLkNsYWltc0lkZW50aXR5Ozc3ODlmMDlkLWUwNTMtNGYyZS1iZGVlLTBjOGY4NDc2YTRiYw"
    },
    {
      "subjectKind": "user",
      "metaType": "member",
      "cuid": "ddd94918-1fc8-459b-994a-cca86c4fbe95",
      "domain": "TEAM FOUNDATION",
      "principalName": "Anonymous",
      "mailAddress": "",
      "origin": "vsts",
      "originId": "ddd94918-1fc8-459b-994a-cca86c4fbe95",
      "displayName": "Anonymous",
      "_links": {
        "self": {
          "href": "https://fabrikam.vssps.visualstudio.com/_apis/graph/users/TWljcm9zb2Z0LlRlYW1Gb3VuZGF0aW9uLlVuYXV0aGVudGljYXRlZElkZW50aXR5O1MtMS0wLTA"
        },
        "memberships": {
          "href": "https://fabrikam.vssps.visualstudio.com/_apis/graph/memberships/TWljcm9zb2Z0LlRlYW1Gb3VuZGF0aW9uLlVuYXV0aGVudGljYXRlZElkZW50aXR5O1MtMS0wLTA"
        }
      },
      "url": "https://fabrikam.vssps.visualstudio.com/_apis/graph/users/TWljcm9zb2Z0LlRlYW1Gb3VuZGF0aW9uLlVuYXV0aGVudGljYXRlZElkZW50aXR5O1MtMS0wLTA",
      "descriptor": "TWljcm9zb2Z0LlRlYW1Gb3VuZGF0aW9uLlVuYXV0aGVudGljYXRlZElkZW50aXR5O1MtMS0wLTA"
    },
    {
      "subjectKind": "user",
      "metaType": "member",
      "cuid": "65903f92-53dc-61b3-bb0e-e69cfa1cb719",
      "domain": "45aa3d2d-7442-473d-b4d3-3c670da9dd96",
      "principalName": "ftotten@vscsi.us",
      "mailAddress": "ftotten@vscsi.us",
      "origin": "aad",
      "originId": "4be8f294-000d-4431-8506-57420b88e204",
      "displayName": "Francis Totten",
      "_links": {
        "self": {
          "href": "https://fabrikam.vssps.visualstudio.com/_apis/graph/users/TWljcm9zb2Z0LklkZW50aXR5TW9kZWwuQ2xhaW1zLkNsYWltc0lkZW50aXR5OzQ1YWEzZDJkLTc0NDItNDczZC1iNGQzLTNjNjcwZGE5ZGQ5NlxmdG90dGVuQHZzY3NpLnVz"
        },
        "memberships": {
          "href": "https://fabrikam.vssps.visualstudio.com/_apis/graph/memberships/TWljcm9zb2Z0LklkZW50aXR5TW9kZWwuQ2xhaW1zLkNsYWltc0lkZW50aXR5OzQ1YWEzZDJkLTc0NDItNDczZC1iNGQzLTNjNjcwZGE5ZGQ5NlxmdG90dGVuQHZzY3NpLnVz"
        }
      },
      "url": "https://fabrikam.vssps.visualstudio.com/_apis/graph/users/TWljcm9zb2Z0LklkZW50aXR5TW9kZWwuQ2xhaW1zLkNsYWltc0lkZW50aXR5OzQ1YWEzZDJkLTc0NDItNDczZC1iNGQzLTNjNjcwZGE5ZGQ5NlxmdG90dGVuQHZzY3NpLnVz",
      "descriptor": "TWljcm9zb2Z0LklkZW50aXR5TW9kZWwuQ2xhaW1zLkNsYWltc0lkZW50aXR5OzQ1YWEzZDJkLTc0NDItNDczZC1iNGQzLTNjNjcwZGE5ZGQ5NlxmdG90dGVuQHZzY3NpLnVz"
    }
  ]
}
"""
CREATE_SUBSCRIPTION = {
    'id': 'fd672255-8b6b-4769-9260-beea83d752ce',
    'url': 'https://fabrikam.visualstudio.com/_apis/hooks/subscriptions/fd672255-8b6b-4769-9260-beea83d752ce',
    'publisherId': 'tfs',
    'eventType': 'workitem.update',
    'resourceVersion': '1.0-preview.1',
    'eventDescription': 'WorkItem Updated',
    'consumerId': 'webHooks',
    'consumerActionId': 'httpRequest',
    'actionDescription': 'To host myservice',
    'createdBy': {
        'id': '00ca946b-2fe9-4f2a-ae2f-40d5c48001bc'
    },
    'createdDate': '2014-10-27T15:37:24.873Z',
    'modifiedBy': {
        'id': '00ca946b-2fe9-4f2a-ae2f-40d5c48001bc'
    },
    'modifiedDate': '2014-10-27T15:37:26.23Z',
    'publisherInputs': {
        'buildStatus': 'Failed',
        'definitionName': 'MyWebSite CI',
        'hostId': 'd81542e4-cdfa-4333-b082-1ae2d6c3ad16',
        'projectId': '6ce954b1-ce1f-45d1-b94d-e6bf2464ba2c',
        'tfsSubscriptionId': '3e8b33e7-426d-4c92-9bf9-58e163dd7dd5'
    },
    'consumerInputs': {
        'url': 'https://myservice/newreceiver'
    }
}

WORK_ITEM_UPDATED = {
    u'resourceContainers': {
        u'project': {u'id': u'c0bf429a-c03c-4a99-9336-d45be74db5a6', u'baseUrl': u'https://laurynsentry.visualstudio.com/'},
        u'account': {u'id': u'90e9a854-eb98-4c56-ae1a-035a0f331dd6', u'baseUrl': u'https://laurynsentry.visualstudio.com/'},
        u'collection': {u'id': u'80ded3e8-3cd3-43b1-9f96-52032624aa3a', u'baseUrl': u'https://laurynsentry.visualstudio.com/'}
    },
    u'resource': {
        u'revisedBy': {
            u'displayName': u'lauryn', u'name': u'lauryn <lauryn@sentry.io>', u'url': u'https://app.vssps.visualstudio.com/A90e9a854-eb98-4c56-ae1a-035a0f331dd6/_apis/Identities/21354f98-ab06-67d9-b974-5a54d992082e', u'imageUrl': u'https://laurynsentry.visualstudio.com/_api/_common/identityImage?id=21354f98-ab06-67d9-b974-5a54d992082e', u'descriptor': u'msa.MjEzNTRmOTgtYWIwNi03N2Q5LWI5NzQtNWE1NGQ5OTIwODJl', u'_links': {u'avatar': {u'href': u'https://laurynsentry.visualstudio.com/_apis/GraphProfile/MemberAvatars/msa.MjEzNTRmOTgtYWIwNi03N2Q5LWI5NzQtNWE1NGQ5OTIwODJl'}},
            u'uniqueName': u'lauryn@sentry.io', u'id': u'21354f98-ab06-67d9-b974-5a54d992082e'
        },
        u'revisedDate': u'9999-01-01T00:00:00Z',
        u'url': u'https://laurynsentry.visualstudio.com/c0bf429a-c03c-4a99-9336-d45be74db5a6/_apis/wit/workItems/31/updates/2',
        u'fields': {
            u'System.AuthorizedDate': {u'newValue': u'2018-07-05T20:52:14.777Z', u'oldValue': u'2018-07-05T20:51:58.927Z'},
            u'System.AssignedTo': {u'newValue': u'lauryn <lauryn@sentry.io>', u'oldValue': u'lauryn2 <lauryn2@sentry.io>'},
            u'System.Watermark': {u'newValue': 78, u'oldValue': 77},
            u'System.Rev': {u'newValue': 2, u'oldValue': 1},
            u'System.RevisedDate': {u'newValue': u'9999-01-01T00:00:00Z', u'oldValue': u'2018-07-05T20:52:14.777Z'},
            u'System.ChangedDate': {u'newValue': u'2018-07-05T20:52:14.777Z', u'oldValue': u'2018-07-05T20:51:58.927Z'}
        },
        u'workItemId': 31,
        u'rev': 2,
        u'_links': {
            u'self': {u'href': u'https://laurynsentry.visualstudio.com/c0bf429a-c03c-4a99-9336-d45be74db5a6/_apis/wit/workItems/31/updates/2'},
            u'workItemUpdates': {u'href': u'https://laurynsentry.visualstudio.com/c0bf429a-c03c-4a99-9336-d45be74db5a6/_apis/wit/workItems/31/updates'},
            u'html': {u'href': u'https://laurynsentry.visualstudio.com/web/wi.aspx?pcguid=80ded3e8-3cd3-43b1-9f96-52032624aa3a&id=31'},
            u'parent': {u'href': u'https://laurynsentry.visualstudio.com/c0bf429a-c03c-4a99-9336-d45be74db5a6/_apis/wit/workItems/31'}
        },
        u'id': 2,
        u'revision': {
            u'url': u'https://laurynsentry.visualstudio.com/c0bf429a-c03c-4a99-9336-d45be74db5a6/_apis/wit/workItems/31/revisions/2',
            u'fields': {
                u'System.AreaPath': u'MyFirstProject',
                u'System.WorkItemType': u'Bug',
                u'System.Reason': u'New',
                u'System.Title': u"NameError: global name 'BitbucketRepositoryProvider' is not defined",
                u'Microsoft.VSTS.Common.Priority': 2,
                u'System.CreatedBy': u'lauryn <lauryn@sentry.io>',
                u'System.AssignedTo': u'lauryn <lauryn@sentry.io>',
                u'System.CreatedDate': u'2018-07-05T20:51:58.927Z',
                u'System.TeamProject': u'MyFirstProject',
                u'Microsoft.VSTS.Common.Severity': u'3 - Medium',
                u'Microsoft.VSTS.Common.ValueArea': u'Business',
                u'System.State': u'New',
                u'System.Description': u'<p><a href="https://lauryn.ngrok.io/sentry/internal/issues/55/">https://lauryn.ngrok.io/sentry/internal/issues/55/</a></p>\n<pre><code>NameError: global name \'BitbucketRepositoryProvider\' is not defined\n(1 additional frame(s) were not displayed)\n...\n  File &quot;sentry/runner/__init__.py&quot;, line 125, in configure\n    configure(ctx, py, yaml, skip_service_validation)\n  File &quot;sentry/runner/settings.py&quot;, line 152, in configure\n    skip_service_validation=skip_service_validation\n  File &quot;sentry/runner/initializer.py&quot;, line 315, in initialize_app\n    register_plugins(settings)\n  File &quot;sentry/runner/initializer.py&quot;, line 60, in register_plugins\n    integration.setup()\n  File &quot;sentry/integrations/bitbucket/integration.py&quot;, line 78, in setup\n    BitbucketRepositoryProvider,\n\nNameError: global name \'BitbucketRepositoryProvider\' is not defined\n</code></pre>\n',
                u'System.ChangedBy': u'lauryn <lauryn@sentry.io>',
                u'System.ChangedDate': u'2018-07-05T20:52:14.777Z',
                u'Microsoft.VSTS.Common.StateChangeDate': u'2018-07-05T20:51:58.927Z',
                u'System.IterationPath': u'MyFirstProject'},
            u'rev': 2,
            u'id': 31,
            u'_links': {u'self': {u'href': u'https://laurynsentry.visualstudio.com/c0bf429a-c03c-4a99-9336-d45be74db5a6/_apis/wit/workItems/31/revisions/2'}, u'workItemRevisions': {u'href': u'https://laurynsentry.visualstudio.com/c0bf429a-c03c-4a99-9336-d45be74db5a6/_apis/wit/workItems/31/revisions'}, u'parent': {u'href': u'https://laurynsentry.visualstudio.com/c0bf429a-c03c-4a99-9336-d45be74db5a6/_apis/wit/workItems/31'}}
        }
    },
    u'eventType': u'workitem.updated',
    u'detailedMessage': None,
    u'createdDate': u'2018-07-05T20:52:16.3051288Z',
    u'id': u'18f51331-2640-4bce-9ebd-c59c855956a2',
    u'resourceVersion': u'1.0',
    u'notificationId': 1,
    u'subscriptionId': u'7bf628eb-b3a7-4fb2-ab4d-8b60f2e8cb9b',
    u'publisherId': u'tfs',
    u'message': None
}


WORK_ITEM_UNASSIGNED = {
    u'resourceContainers': {
        u'project': {
            u'id': u'c0bf429a-c03c-4a99-9336-d45be74db5a6',
            u'baseUrl': u'https://laurynsentry.visualstudio.com/'
        },
        u'account': {
            u'id': u'90e9a854-eb98-4c56-ae1a-035a0f331dd6',
            u'baseUrl': u'https://laurynsentry.visualstudio.com/'
        },
        u'collection': {
            u'id': u'80ded3e8-3cd3-43b1-9f96-52032624aa3a',
            u'baseUrl': u'https://laurynsentry.visualstudio.com/'
        }
    },
    u'resource': {
        u'revisedBy': {
            u'displayName': u'lauryn',
            u'name': u'lauryn <lauryn@sentry.io>',
            u'url': u'https://app.vssps.visualstudio.com/A90e9a854-eb98-4c56-ae1a-035a0f331dd6/_apis/Identities/21354f98-ab06-67d9-b974-5a54d992082e',
            u'imageUrl': u'https://laurynsentry.visualstudio.com/_api/_common/identityImage?id=21354f98-ab06-67d9-b974-5a54d992082e',
            u'descriptor': u'msa.MjEzNTRmOTgtYWIwNi03N2Q5LWI5NzQtNWE1NGQ5OTIwODJl',
            u'_links': {
                u'avatar': {
                    u'href': u'https://laurynsentry.visualstudio.com/_apis/GraphProfile/MemberAvatars/msa.MjEzNTRmOTgtYWIwNi03N2Q5LWI5NzQtNWE1NGQ5OTIwODJl'
                }
            },
            u'uniqueName': u'lauryn@sentry.io',
            u'id': u'21354f98-ab06-67d9-b974-5a54d992082e'
        },
        u'revisedDate': u'9999-01-01T00:00:00      Z',
        u'url': u'https://laurynsentry.visualstudio.com/c0bf429a-c03c-4a99-9336-d45be74db5a6/_apis/wit/workItems/33/updates/3',
        u'fields': {
            u'System.AuthorizedDate': {
                u'newValue': u'2018-07-05T23:23:09.493            Z',
                u'oldValue': u'2018-07-05T23:21:38.243            Z'
            },
            u'System.AssignedTo': {
                u'oldValue': u'lauryn <lauryn@sentry.io>'
            },
            u'System.Watermark': {
                u'newValue': 83,
                u'oldValue': 82
            },
            u'System.Rev': {
                u'newValue': 3,
                u'oldValue': 2
            },
            u'System.RevisedDate': {
                u'newValue': u'9999-01-01T00:00:00            Z',
                u'oldValue': u'2018-07-05T23:23:09.493            Z'
            },
            u'System.ChangedDate': {
                u'newValue': u'2018-07-05T23:23:09.493            Z',
                u'oldValue': u'2018-07-05T23:21:38.243            Z'
            }
        },
        u'workItemId': 33,
        u'rev': 3,
        u'_links': {
            u'self': {
                u'href': u'https://laurynsentry.visualstudio.com/c0bf429a-c03c-4a99-9336-d45be74db5a6/_apis/wit/workItems/33/updates/3'
            },
            u'workItemUpdates': {
                u'href': u'https://laurynsentry.visualstudio.com/c0bf429a-c03c-4a99-9336-d45be74db5a6/_apis/wit/workItems/33/updates'
            },
            u'html': {
                u'href': u'https://laurynsentry.visualstudio.com/web/wi.aspx?pcguid=80ded3e8-3cd3-43b1-9f96-52032624aa3a&id=33'
            },
            u'parent': {
                u'href': u'https://laurynsentry.visualstudio.com/c0bf429a-c03c-4a99-9336-d45be74db5a6/_apis/wit/workItems/33'
            }
        },
        u'id': 3,
        u'revision': {
            u'url': u'https://laurynsentry.visualstudio.com/c0bf429a-c03c-4a99-9336-d45be74db5a6/_apis/wit/workItems/33/revisions/3',
            u'fields': {
                u'System.AreaPath': u'MyFirstProject',
                u'System.WorkItemType': u'Bug',
                u'System.Reason': u'New',
                u'System.Title': u'NotImplementedError:Visual Studio Team Services requires an organization_id',
                u'Microsoft.VSTS.Common.Priority': 2,
                u'System.CreatedBy': u'lauryn <lauryn@sentry.io>',
                u'Microsoft.VSTS.Common.StateChangeDate': u'2018-07-05T23:21:25.847            Z',
                u'System.CreatedDate': u'2018-07-05T23:21:25.847            Z',
                u'System.TeamProject': u'MyFirstProject',
                u'Microsoft.VSTS.Common.ValueArea': u'Business',
                u'System.State': u'New',
                u'System.Description': u'<p><a href="https:            //lauryn.ngrok.io/sentry/internal/issues/196/">https:            //lauryn.ngrok.io/sentry/internal/issues/196/</a></p>\n<pre><code>NotImplementedError:Visual Studio Team Services requires an organization_id\n(57 additional frame(s) were not displayed)\n...\n  File &quot;sentry/tasks/base.py&quot;',
                u'System.ChangedBy': u'lauryn <lauryn@sentry.io>',
                u'System.ChangedDate': u'2018-07-05T23:23:09.493            Z',
                u'Microsoft.VSTS.Common.Severity': u'3 - Medium',
                u'System.IterationPath': u'MyFirstProject'
            },
            u'rev': 3,
            u'id': 33,
            u'_links': {
                u'self': {
                    u'href': u'https://laurynsentry.visualstudio.com/c0bf429a-c03c-4a99-9336-d45be74db5a6/_apis/wit/workItems/33/revisions/3'
                },
                u'workItemRevisions': {
                    u'href': u'https://laurynsentry.visualstudio.com/c0bf429a-c03c-4a99-9336-d45be74db5a6/_apis/wit/workItems/33/revisions'
                },
                u'parent': {
                    u'href': u'https://laurynsentry.visualstudio.com/c0bf429a-c03c-4a99-9336-d45be74db5a6/_apis/wit/workItems/33'
                }
            }
        }
    },
    u'eventType': u'workitem.updated',
    u'detailedMessage': None,
    u'createdDate': u'2018-07-05T23:23:11.1935112   Z',
    u'id': u'cc349c85-6595-4939-9b69-f89480be6a26',
    u'resourceVersion': u'1.0',
    u'notificationId': 2,
    u'subscriptionId': u'7405a600-6a25-48e6-81b6-1dde044783ad',
    u'publisherId': u'tfs',
    u'message': None
}
WORK_ITEM_UPDATED_STATUS = {
    u'resourceContainers': {
        u'project': {
            u'id': u'c0bf429a-c03c-4a99-9336-d45be74db5a6',
            u'baseUrl': u'https://laurynsentry.visualstudio.com/'
        },
        u'account': {
            u'id': u'90e9a854-eb98-4c56-ae1a-035a0f331dd6',
            u'baseUrl': u'https://laurynsentry.visualstudio.com/'
        },
        u'collection': {
            u'id': u'80ded3e8-3cd3-43b1-9f96-52032624aa3a',
            u'baseUrl': u'https://laurynsentry.visualstudio.com/'
        }
    },
    u'resource': {
        u'revisedBy': {
            u'displayName': u'lauryn',
            u'name': u'lauryn <lauryn@sentry.io>',
            u'url': u'https://app.vssps.visualstudio.com/A90e9a854-eb98-4c56-ae1a-035a0f331dd6/_apis/Identities/21354f98-ab06-67d9-b974-5a54d992082e',
            u'imageUrl': u'https://laurynsentry.visualstudio.com/_api/_common/identityImage?id=21354f98-ab06-67d9-b974-5a54d992082e',
            u'descriptor': u'msa.MjEzNTRmOTgtYWIwNi03N2Q5LWI5NzQtNWE1NGQ5OTIwODJl',
            u'_links': {
                u'avatar': {
                    u'href': u'https://laurynsentry.visualstudio.com/_apis/GraphProfile/MemberAvatars/msa.MjEzNTRmOTgtYWIwNi03N2Q5LWI5NzQtNWE1NGQ5OTIwODJl'
                }
            },
            u'uniqueName': u'lauryn@sentry.io',
            u'id': u'21354f98-ab06-67d9-b974-5a54d992082e'
        },
        u'revisedDate': u'9999-01-01T00:00:00      Z',
        u'url': u'https://laurynsentry.visualstudio.com/c0bf429a-c03c-4a99-9336-d45be74db5a6/_apis/wit/workItems/33/updates/3',
        u'fields': {
            u'System.AuthorizedDate': {
                u'newValue': u'2018-07-05T23:23:09.493            Z',
                u'oldValue': u'2018-07-05T23:21:38.243            Z'
            },
            u'System.State': {
                u'oldValue': u'New',
                u'newValue': u'Resolved'
            },
            u'System.Watermark': {
                u'newValue': 83,
                u'oldValue': 82
            },
            u'System.Rev': {
                u'newValue': 3,
                u'oldValue': 2
            },
            u'System.RevisedDate': {
                u'newValue': u'9999-01-01T00:00:00            Z',
                u'oldValue': u'2018-07-05T23:23:09.493            Z'
            },
            u'System.ChangedDate': {
                u'newValue': u'2018-07-05T23:23:09.493            Z',
                u'oldValue': u'2018-07-05T23:21:38.243            Z'
            }
        },
        u'workItemId': 33,
        u'rev': 3,
        u'_links': {
            u'self': {
                u'href': u'https://laurynsentry.visualstudio.com/c0bf429a-c03c-4a99-9336-d45be74db5a6/_apis/wit/workItems/33/updates/3'
            },
            u'workItemUpdates': {
                u'href': u'https://laurynsentry.visualstudio.com/c0bf429a-c03c-4a99-9336-d45be74db5a6/_apis/wit/workItems/33/updates'
            },
            u'html': {
                u'href': u'https://laurynsentry.visualstudio.com/web/wi.aspx?pcguid=80ded3e8-3cd3-43b1-9f96-52032624aa3a&id=33'
            },
            u'parent': {
                u'href': u'https://laurynsentry.visualstudio.com/c0bf429a-c03c-4a99-9336-d45be74db5a6/_apis/wit/workItems/33'
            }
        },
        u'id': 3,
        u'revision': {
            u'url': u'https://laurynsentry.visualstudio.com/c0bf429a-c03c-4a99-9336-d45be74db5a6/_apis/wit/workItems/33/revisions/3',
            u'fields': {
                u'System.AreaPath': u'MyFirstProject',
                u'System.WorkItemType': u'Bug',
                u'System.Reason': u'New',
                u'System.Title': u'NotImplementedError:Visual Studio Team Services requires an organization_id',
                u'Microsoft.VSTS.Common.Priority': 2,
                u'System.CreatedBy': u'lauryn <lauryn@sentry.io>',
                u'Microsoft.VSTS.Common.StateChangeDate': u'2018-07-05T23:21:25.847            Z',
                u'System.CreatedDate': u'2018-07-05T23:21:25.847            Z',
                u'System.TeamProject': u'MyFirstProject',
                u'Microsoft.VSTS.Common.ValueArea': u'Business',
                u'System.State': u'New',
                u'System.Description': u'<p><a href="https:            //lauryn.ngrok.io/sentry/internal/issues/196/">https:            //lauryn.ngrok.io/sentry/internal/issues/196/</a></p>\n<pre><code>NotImplementedError:Visual Studio Team Services requires an organization_id\n(57 additional frame(s) were not displayed)\n...\n  File &quot;sentry/tasks/base.py&quot;',
                u'System.ChangedBy': u'lauryn <lauryn@sentry.io>',
                u'System.ChangedDate': u'2018-07-05T23:23:09.493            Z',
                u'Microsoft.VSTS.Common.Severity': u'3 - Medium',
                u'System.IterationPath': u'MyFirstProject'
            },
            u'rev': 3,
            u'id': 33,
            u'_links': {
                u'self': {
                    u'href': u'https://laurynsentry.visualstudio.com/c0bf429a-c03c-4a99-9336-d45be74db5a6/_apis/wit/workItems/33/revisions/3'
                },
                u'workItemRevisions': {
                    u'href': u'https://laurynsentry.visualstudio.com/c0bf429a-c03c-4a99-9336-d45be74db5a6/_apis/wit/workItems/33/revisions'
                },
                u'parent': {
                    u'href': u'https://laurynsentry.visualstudio.com/c0bf429a-c03c-4a99-9336-d45be74db5a6/_apis/wit/workItems/33'
                }
            }
        }
    },
    u'eventType': u'workitem.updated',
    u'detailedMessage': None,
    u'createdDate': u'2018-07-05T23:23:11.1935112   Z',
    u'id': u'cc349c85-6595-4939-9b69-f89480be6a26',
    u'resourceVersion': u'1.0',
    u'notificationId': 2,
    u'subscriptionId': u'7405a600-6a25-48e6-81b6-1dde044783ad',
    u'publisherId': u'tfs',
    u'message': None
}

WORK_ITEM_STATES = {
    'count': 5,
    'value': [
        {
            'name': 'New',
            'color': 'b2b2b2',
            'category': 'Proposed'
        },
        {
            'name': 'Active',
            'color': '007acc',
            'category': 'InProgress'
        },
        {
            'name': 'CustomState',
            'color': '5688E0',
            'category': 'InProgress'
        },
        {
            'name': 'Resolved',
            'color': 'ff9d00',
            'category': 'Resolved'
        },
        {
            'name': 'Closed',
            'color': '339933',
            'category': 'Completed'
        }
    ]
}

GET_PROJECTS_RESPONSE = """{
    "count": 1,
    "value": [{
        "id": "ac7c05bb-7f8e-4880-85a6-e08f37fd4a10",
        "name": "Fabrikam-Fiber-Git",
        "url": "https://jess-dev.visualstudio.com/_apis/projects/ac7c05bb-7f8e-4880-85a6-e08f37fd4a10",
        "state": "wellFormed",
        "revision": 16,
        "visibility": "private"
    }]
}"""

PR_WEBHOOK = {
    'id': '6872ee8c-b333-4eff-bfb9-0d5274943566',
    'eventType': 'git.pullrequest.merged',
    'publisherId': 'tfs',
    'scope': 'all',
    'message': {
        'text': 'Jamal Hartnett has created a pull request merge commit',
        'html': 'Jamal Hartnett has created a pull request merge commit',
        'markdown': 'Jamal Hartnett has created a pull request merge commit'
    },
    'detailedMessage': {
        'text': 'Jamal Hartnett has created a pull request merge commit\r\n\r\n- Merge status: Succeeded\r\n- Merge commit: eef717(https://fabrikam.visualstudio.com/DefaultCollection/_apis/repos/git/repositories/4bc14d40-c903-45e2-872e-0462c7748079/commits/eef717f69257a6333f221566c1c987dc94cc0d72)\r\n',
        'html': 'Jamal Hartnett has created a pull request merge commit\r\n<ul>\r\n<li>Merge status: Succeeded</li>\r\n<li>Merge commit: <a href=\'https://fabrikam.visualstudio.com/DefaultCollection/_apis/repos/git/repositories/4bc14d40-c903-45e2-872e-0462c7748079/commits/eef717f69257a6333f221566c1c987dc94cc0d72\'>eef717</a></li>\r\n</ul>',
        'markdown': 'Jamal Hartnett has created a pull request merge commit\r\n\r\n+ Merge status: Succeeded\r\n+ Merge commit: [eef717](https://fabrikam.visualstudio.com/DefaultCollection/_apis/repos/git/repositories/4bc14d40-c903-45e2-872e-0462c7748079/commits/eef717f69257a6333f221566c1c987dc94cc0d72)\r\n'
    },
    'resource': {
        'repository': {
            'id': '4bc14d40-c903-45e2-872e-0462c7748079',
            'name': 'Fabrikam',
            'url': 'https://fabrikam.visualstudio.com/DefaultCollection/_apis/repos/git/repositories/4bc14d40-c903-45e2-872e-0462c7748079',
            'project': {
                'id': '6ce954b1-ce1f-45d1-b94d-e6bf2464ba2c',
                'name': 'Fabrikam',
                'url': 'https://fabrikam.visualstudio.com/DefaultCollection/_apis/projects/6ce954b1-ce1f-45d1-b94d-e6bf2464ba2c',
                'state': 'wellFormed'
            },
            'defaultBranch': 'refs/heads/master',
            'remoteUrl': 'https://fabrikam.visualstudio.com/DefaultCollection/_git/Fabrikam'
        },
        'pullRequestId': 1,
        'status': 'completed',
        'createdBy': {
            'id': '54d125f7-69f7-4191-904f-c5b96b6261c8',
            'displayName': 'Jamal Hartnett',
            'uniqueName': 'fabrikamfiber4@hotmail.com',
            'url': 'https://fabrikam.vssps.visualstudio.com/_apis/Identities/54d125f7-69f7-4191-904f-c5b96b6261c8',
            'imageUrl': 'https://fabrikam.visualstudio.com/DefaultCollection/_api/_common/identityImage?id=54d125f7-69f7-4191-904f-c5b96b6261c8'
        },
        'creationDate': '2014-06-17T16:55:46.589889Z',
        'closedDate': '2014-06-30T18:59:12.3660573Z',
        'title': 'my first pull request',
        'description': ' - test2\r\n',
        'sourceRefName': 'refs/heads/mytopic',
        'targetRefName': 'refs/heads/master',
        'mergeStatus': 'succeeded',
        'mergeId': 'a10bb228-6ba6-4362-abd7-49ea21333dbd',
        'lastMergeSourceCommit': {
            'commitId': '53d54ac915144006c2c9e90d2c7d3880920db49c',
            'url': 'https://fabrikam.visualstudio.com/DefaultCollection/_apis/repos/git/repositories/4bc14d40-c903-45e2-872e-0462c7748079/commits/53d54ac915144006c2c9e90d2c7d3880920db49c'
        },
        'lastMergeTargetCommit': {
            'commitId': 'a511f535b1ea495ee0c903badb68fbc83772c882',
            'url': 'https://fabrikam.visualstudio.com/DefaultCollection/_apis/repos/git/repositories/4bc14d40-c903-45e2-872e-0462c7748079/commits/a511f535b1ea495ee0c903badb68fbc83772c882'
        },
        'lastMergeCommit': {
            'commitId': 'eef717f69257a6333f221566c1c987dc94cc0d72',
            'url': 'https://fabrikam.visualstudio.com/DefaultCollection/_apis/repos/git/repositories/4bc14d40-c903-45e2-872e-0462c7748079/commits/eef717f69257a6333f221566c1c987dc94cc0d72'
        },
        'reviewers': [
            {
                'reviewerUrl': None,
                'vote': 0,
                'id': '2ea2d095-48f9-4cd6-9966-62f6f574096c',
                'displayName': '[Mobile]\\Mobile Team',
                'uniqueName': 'vstfs:///Classification/TeamProject/f0811a3b-8c8a-4e43-a3bf-9a049b4835bd\\Mobile Team',
                'url': 'https://fabrikam.vssps.visualstudio.com/_apis/Identities/2ea2d095-48f9-4cd6-9966-62f6f574096c',
                'imageUrl': 'https://fabrikam.visualstudio.com/DefaultCollection/_api/_common/identityImage?id=2ea2d095-48f9-4cd6-9966-62f6f574096c',
                'isContainer': True
            }
        ],
        'url': 'https://fabrikam.visualstudio.com/DefaultCollection/_apis/repos/git/repositories/4bc14d40-c903-45e2-872e-0462c7748079/pullRequests/1'
    },
    'resourceVersion': '1.0',
    'resourceContainers': {
        'collection': {
            'id': 'c12d0eb8-e382-443b-9f9c-c52cba5014c2'
        },
        'account': {
            'id': 'f844ec47-a9db-4511-8281-8b63f4eaf94e'
        },
        'project': {
            'id': 'be9b3917-87e6-42a4-a549-2bc06a7a878f'
        }
    },
    'createdDate': '2016-09-19T13:03:27.3156388Z'
}
