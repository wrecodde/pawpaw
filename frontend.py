
import os

import flask
from flask import Flask, render_template
from flask_restplus import Api, Resource, reqparse
import requests

import google.oauth2
from google.oauth2 import id_token
import google_auth_oauthlib
import googleapiclient.discovery
from google.auth.transport import requests

from dotenv import load_dotenv
load_dotenv()

CLIENT_SECRETS_FILE = "env/client_secret.json"
CLIENT_ID = os.getenv('G_API_CLIENT_ID')
SCOPES = ['https://www.googleapis.com/auth/userinfo.profile']
API_SERVICE_NAME = 'people'
API_VERSION = 'v1'

app = Flask(__name__)
app.secret_key = os.getenv('G_API_SECRET')

@app.route('/')
def root_view():
    return render_template('index.html')

api = Api(app, doc=False)

@api.route('/profile')
class Profile(Resource):
    """Profile Endpoint fetches profile info related to the signed account.
    """

    def get(self):
        if 'credentials' not in flask.session:
            return flask.redirect(api.url_for(GetAuthorization))
            # return {'msg': 'You must sign in first.'}
        
        credentials = google.oauth2.credentials.Credentials(
            **flask.session['credentials']
        )
        people_service = googleapiclient.discovery.build(
            API_SERVICE_NAME,
            API_VERSION,
            credentials=credentials
        )
        # peopele api service (https://developers.google.com/people/v1/profiles#python)
        profile = people_service.people().get(
            resourceName='people/me', personFields='names,emailAddresses'
        ).execute()
        name = profile['names'][0]['displayName']

        # flask session is used to pass state info between methods/endpoints
        flask.session['credentials'] = credentials_to_dict(credentials)

        return {'name': name, 'revoke_url': '/revoke', 'creds': flask.session['credentials']}
    
@api.route('/authorize')
class GetAuthorization(Resource):
    """Authorization Endpoint begins the authentication process, requesting
    access to the User's Google Account.
    """

    def get(self):
        # creating OAuth Flow
        flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
            CLIENT_SECRETS_FILE,
            scopes=SCOPES
        )
        flow.redirect_uri = api.url_for(OAuthCallback, _external=True)

        # construct and redirect app to OAuth URL
        authorization_url, state = flow.authorization_url(
            access_type='offline',
            inlucde_granted_scopes='true'
        )

        # flask session is used to pass state data in between methods/endpoints
        flask.session['state'] = state
        return flask.redirect(authorization_url)

@api.route('/oauth2callback')
class OAuthCallback(Resource):
    """Endpoint completes the OAuth process
    """

    def get(self):
        state = flask.session['state']

        # continue oauth flow
        flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
            CLIENT_SECRETS_FILE,
            scopes=SCOPES,
            state=state
        )
        flow.redirect_uri = api.url_for(OAuthCallback, _external=True)
        
        # completing the oatuh process, access tokens and credentials are issued
        authorization_response = flask.request.url
        flow.fetch_token(authorization_response=authorization_response)

        # credentials are stored in flask.session. in prod, persistent storage will be used
        credentials = flow.credentials
        flask.session['credentials'] = credentials_to_dict(credentials)

        # authentication is complete, redirect to /profile
        return flask.redirect(api.url_for(Profile))

@api.route('/revoke')
class Revoke(Resource):
    """Revoke Endpoint effectively logs a user out from the app.
    """

    def get(self):
        if 'credentials' not in flask.session:
            # no user is logged in
            return {'msg': 'OAuth unavailable.', 'authorization_url': '/authorize'}
        
        credentials = google.oauth2.credentials.Credentials(
            **flask.session['credentials']
        )

        # revoke given access tokens and credentials
        revoke = requests.post(
            'https://oauth2.googleapis.com/revoke',
            params={'token': credentials.token},
            headers={'content-type': 'application/x-www-form-urlencoded'}
        )
        if revoke.status_code == 200:
            # also clear credentials on the way out..
            ClearCredentials().get()
            return {'msg': 'Credentials successfully revoked.', 'next_url': '/'}
        else:
            return {'msg': 'An error occured.'}, 500

@api.route('/clear')
class ClearCredentials(Resource):
    """Endpoint clears temporarily stored access credentials.
    """

    def get(self):
        if 'credentials' in flask.session:
            del flask.session['credentials']
        return {'msg': 'Credentials have been cleared.', 'next_url': '/'}


def credentials_to_dict(credentials):
  return {'token': credentials.token,
          'refresh_token': credentials.refresh_token,
          'token_uri': credentials.token_uri,
          'client_id': credentials.client_id,
          'client_secret': credentials.client_secret,
          'scopes': credentials.scopes}

if __name__ == "__main__":
    debug = True if os.getenv('DEBUG_APP') == 'True' else False
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
    app.run('localhost', 8080, debug=debug)

