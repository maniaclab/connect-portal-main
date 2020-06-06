from flask import (flash, redirect, render_template, request,
                   session, url_for, jsonify)
import requests
import json

try:
    from urllib.parse import urlencode
except ImportError:
    from urllib import urlencode

from portal import app, csrf
from portal.decorators import authenticated
from portal.utils import (load_portal_client, get_safe_redirect, flash_message_parser)
from portal.connect_api import (get_user_info, get_user_group_memberships,
                            get_multiplex, get_user_connect_status,
                            get_user_pending_project_requests,
                            get_group_info, get_group_members,
                            delete_group_entry, update_user_group_status,
                            get_user_access_token)
# Use these four lines on container
import sys
import subprocess
import os
import signal

# Read configurable tokens and endpoints from config file, values must be set
ciconnect_api_token = app.config['CONNECT_API_TOKEN']
ciconnect_api_endpoint = app.config['CONNECT_API_ENDPOINT']
mailgun_api_token = app.config['MAILGUN_API_TOKEN']
# slate_api_token = app.config['SLATE_API_TOKEN']
# slate_api_endpoint = app.config['SLATE_API_ENDPOINT']
# Read Brand Dir from config and insert path to read
brand_dir = app.config['MARKDOWN_DIR']
sys.path.insert(0, brand_dir)
# Set sys path and import view routes
sys.path.insert(1, 'portal/views')
import group_views
import error_handling
import users_groups


@app.route('/webhooks/github', methods=['GET', 'POST'])
@csrf.exempt
def webhooks():
    """Endpoint that acepts post requests from Github Webhooks"""

    cmd = """
    cd {}
    git pull origin master
    """.format(brand_dir)

    p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, stdin=subprocess.PIPE)
    out, err = p.communicate()
    print("Return code: {}".format(p.returncode))
    print("Error message: {}".format(err))

    parent_pid = os.getppid()
    print("Parent PID: {}".format(parent_pid))
    os.kill(parent_pid, signal.SIGHUP)

    return out


@app.route('/', methods=['GET'])
def home():
    """Home page - play with it if you must!"""
    domain_name = request.headers['Host']
    if 'usatlas' in domain_name:
        domain_name = 'atlas.ci-connect.net'
    elif 'uscms' in domain_name:
        domain_name = 'cms.ci-connect.net'
    elif 'uchicago' in domain_name:
        domain_name = 'psdconnect.uchicago.edu'

    with open(brand_dir + '/' + domain_name + '/home_content/home_text_headline.md', "r") as file:
        home_text_headline = file.read()
    with open(brand_dir + '/' + domain_name + '/home_content/home_text_rotating.md', "r") as file:
        home_text_rotating = file.read()

    collaborations = [{'name': 'Atlas',
                       'href': 'https://atlas.ci-connect.net',
                       'img': 'img/atlas-connect-logo.png',
                       'description': get_about_markdown("atlas.ci-connect.net")},
                      {'name': 'CMS',
                       'href': 'https://cms.ci-connect.net',
                       'img': 'img/cms-connect-logo.png',
                       'description': get_about_markdown("cms.ci-connect.net")},
                      {'name': 'Duke',
                       'href': 'https://duke.ci-connect.net',
                       'img': 'img/duke-connect-logo.png',
                       'description': get_about_markdown("duke.ci-connect.net")},
                      {'name': 'OSG',
                       'href': 'https://www.osgconnect.net',
                       'img': 'img/osg-connect-logo.png',
                       'description': get_about_markdown("osgconnect.net")},
                      {'name': 'SPT',
                       'href': 'https://spt.ci-connect.net',
                       'img': 'img/spt-connect-logo.png',
                       'description': get_about_markdown("spt.ci-connect.net")},
                      {'name': 'PSD',
                       'href': 'https://psdconnect.uchicago.edu',
                       'img': 'img/psd-connect-logo.png',
                       'description': get_about_markdown("psdconnect.uchicago.edu")}]

    return render_template('home.html', home_text_headline=home_text_headline,
                                        home_text_rotating=home_text_rotating,
                                        collaborations=collaborations)


def get_about_markdown(domain_name):
    with open(brand_dir + '/' + domain_name + '/about/about.md', "r") as file:
        about = file.read()
    return about


@app.route('/support', methods=['POST'])
def support():
    """
    Support page, utilize mailgun to send message
    """
    if request.method == 'POST':
        user_email = request.form['email']
        # print("User Email: {}".format(user_email))
        description = request.form['description']
        # mailgun setup here
        domain_name = request.headers['Host']
        # print(domain_name)
        support_emails = {
                            "cms.ci-connect.net": "cms-connect-support@cern.ch",
                            "duke.ci-connect.net": "scsc@duke.edu",
                            "spt.ci-connect.net": "jlstephen@uchicago.edu",
                            "atlas.ci-connect.net": "atlas-connect-l@lists.bnl.gov",
                            "psdconnect.uchicago.edu": "support@ci-connect.uchicago.edu",
                            "www.ci-connect.net": "support@ci-connect.net",
                            "localhost:5000": "jeremyvan614@gmail.com"
                            }

        try:
            support_email = support_emails[domain_name]
        except:
            support_email = "support@ci-connect.net"
        # print("Support Email: {} {}".format(support_email, mailgun_api_token))
        r = requests.post("https://api.mailgun.net/v3/api.ci-connect.net/messages",
                          auth=('api', mailgun_api_token),
                          data={
                              "from": "<" + user_email + ">",
                              "to": [support_email],
                              "cc": "<{}>".format(user_email),
                              "subject": "Support Inquiry",
                              "text": description
                          })
        if r.status_code == requests.codes.ok:
            flash("Your message has been sent to the support team.", 'success')
            return redirect(url_for('about'))
        else:
            flash("Unable to send message", 'warning')
            return redirect(url_for('about'))


@app.route('/groups/new', methods=['GET', 'POST'])
@authenticated
def create_group():
    """Create groups"""
    access_token = get_user_access_token(session)
    query = {'token': access_token}
    print(query)
    if request.method == 'GET':
        sciences = requests.get(
            ciconnect_api_endpoint + '/v1alpha1/fields_of_science')
        sciences = sciences.json()['fields_of_science']
        return render_template('groups_create.html', sciences=sciences)
    elif request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone']
        description = request.form['description']
        try:
            # Purpose/Field of Science for CMS will always be High Energy Physics
            field_of_science = request.form['field_of_science']
        except:
            field_of_science = "High Energy Physics".decode('utf-8')

        put_group = {"apiVersion": 'v1alpha1', "kind": "Group",
                     'metadata': {'name': name,
                                  'field_of_science': field_of_science,
                                  'email': email, 'phone': phone,
                                  'description': description}}
        create_group = requests.put(
            ciconnect_api_endpoint + '/v1alpha1/groups/root/subgroups/' + name, params=query, json=put_group)
        if create_group.status_code == requests.codes.ok:
            flash_message = flash_message_parser('create_group')
            flash(flash_message, 'success')
            return redirect(url_for('groups'))
        else:
            err_message = create_group.json()['message']
            flash('Failed to create group: {}'.format(err_message), 'warning')
            return redirect(url_for('groups'))


@app.route('/groups/<group_name>/delete', methods=['POST'])
@authenticated
def delete_group(group_name):
    if request.method == 'POST':
        r = delete_group_entry(group_name, session)

        if r.status_code == requests.codes.ok:
            flash_message = flash_message_parser('delete_group')
            flash(flash_message, 'success')
            return redirect(url_for('groups'))
        else:
            err_message = r.json()['message']
            flash('Failed to delete group: {}'.format(err_message), 'warning')
            return redirect(url_for('view_group', group_name=group_name))


@app.route('/groups/<group_name>/add_group_member/<unix_name>', methods=['POST'])
@authenticated
def add_group_member(group_name, unix_name):
    if request.method == 'POST':
        # Add user to group by setting user status to active
        status = 'active'
        user_status = update_user_group_status(group_name, unix_name, status, session)

        if user_status.status_code == requests.codes.ok:
            flash_message = flash_message_parser('add_group_member')
            flash(flash_message, 'success')
            return redirect(url_for('view_group_members', group_name=group_name))
        else:
            err_message = user_status.json()['message']
            flash('Failed to add member to group: {}'.format(
                err_message), 'warning')
            return redirect(url_for('view_group_members', group_name=group_name))


@app.route('/groups/<group_name>/delete_group_member/<unix_name>', methods=['POST'])
@authenticated
def remove_group_member(group_name, unix_name):
    if request.method == 'POST':
        access_token = get_user_access_token(session)
        query = {'token': access_token}
        try:
            message = request.form['denial-message']
            denial_message = {'message': message}
            remove_user = requests.delete(
                ciconnect_api_endpoint + '/v1alpha1/groups/' +
                group_name + '/members/' + unix_name, params=query, json=denial_message)
        except:
            remove_user = requests.delete(
                ciconnect_api_endpoint + '/v1alpha1/groups/' +
                group_name + '/members/' + unix_name, params=query)

        if remove_user.status_code == requests.codes.ok:
            flash_message = flash_message_parser('remove_group_member')
            flash(flash_message, 'success')
            return redirect(url_for('view_group_members', group_name=group_name))
        else:
            err_message = remove_user.json()['message']
            flash('Failed to remove member from group: {}'.format(
                err_message), 'warning')
            return redirect(url_for('view_group_members', group_name=group_name))


@app.route('/groups/<group_name>/admin_group_member/<unix_name>', methods=['POST'])
@authenticated
def admin_group_member(group_name, unix_name):
    if request.method == 'POST':
        status = 'admin'
        user_status = update_user_group_status(group_name, unix_name, status, session)

        if user_status.status_code == requests.codes.ok:
            flash_message = flash_message_parser('admin_group_member')
            flash(flash_message, 'success')
            return redirect(url_for('view_group_members', group_name=group_name))
        else:
            err_message = user_status.json()['message']
            flash('Failed make member an admin: {}'.format(
                err_message), 'warning')
            return redirect(url_for('view_group_members', group_name=group_name))


@app.route('/groups/<group_name>/subgroups/new', methods=['GET', 'POST'])
@authenticated
def create_subgroup(group_name):
    access_token = get_user_access_token(session)
    query = {'token': access_token}
    if request.method == 'GET':
        sciences = requests.get(
            ciconnect_api_endpoint + '/v1alpha1/fields_of_science')
        sciences = sciences.json()['fields_of_science']
        # Get group members
        group_members = get_group_members(group_name, session)
        # Return list of admins of group
        try:
            group_admins = [
                member for member in group_members if member['state'] == 'admin']
        except:
            group_admins = []
        # Check if user status of root connect group specifically
        connect_group = session['url_host']['unix_name']
        unix_name = session['unix_name']
        user_status = get_user_connect_status(unix_name, connect_group)

        # Get group information
        group = get_group_info(group_name, session)
        return render_template('groups_create.html', sciences=sciences,
                                group_name=group_name, group_admins=group_admins,
                                user_status=user_status, group=group)

    elif request.method == 'POST':
        name = request.form['name']
        display_name = request.form['display-name']
        email = request.form['email']
        phone = request.form['phone']
        description = request.form['description']
        try:
            # Purpose/Field of Science for CMS will always be High Energy Physics
            field_of_science = request.form['field_of_science']
        except:
            field_of_science = "High Energy Physics".decode('utf-8')

        put_query = {"apiVersion": 'v1alpha1',
                     'metadata': {'name': name, 'display_name': display_name,
                                  'purpose': field_of_science,
                                  'email': email, 'phone': phone,
                                  'description': description}}

        r = requests.put(
            ciconnect_api_endpoint + '/v1alpha1/groups/' + group_name +
            '/subgroup_requests/' + name, params=query, json=put_query)
        full_created_group_name = group_name + '.' + name

        # Check if user status of root connect group specifically
        connect_group = session['url_host']['unix_name']
        unix_name = session['unix_name']
        user_status = get_user_connect_status(unix_name, connect_group)

        if r.status_code == requests.codes.ok:
            if user_status == 'admin':
                flash_message = flash_message_parser('create_subgroup')
                flash(flash_message, 'success')
                return redirect(url_for('view_group', group_name=full_created_group_name))
            else:
                flash(
                    "The support team has been notified of your requested subgroup.", 'success')
                return redirect(url_for('users_groups_pending'))
        else:
            err_message = r.json()['message']
            flash('Failed to request project creation: {}'.format(
                err_message), 'warning')
            return redirect(url_for('view_group_subgroups_requests', group_name=group_name))


@app.route('/groups/<group_name>/requests/edit', methods=['GET', 'POST'])
@authenticated
def edit_subgroup_requests(group_name):
    access_token = get_user_access_token(session)
    query = {'token': access_token}
    enclosing_group_name = '.'.join(group_name.split('.')[:-1])
    if request.method == 'GET':
        sciences = requests.get(
            ciconnect_api_endpoint + '/v1alpha1/fields_of_science')
        sciences = sciences.json()['fields_of_science']

        group = get_group_info(group_name, session)

        return render_template('groups_requests_edit.html', sciences=sciences,
                                group_name=group_name, group=group)

    elif request.method == 'POST':
        name = request.form['name']
        display_name = request.form['display-name']
        email = request.form['email']
        phone = request.form['phone']
        description = request.form['description']

        new_unix_name = enclosing_group_name + '.' + name

        if new_unix_name == group_name:
            put_query = {"apiVersion": 'v1alpha1',
                         'metadata': {'display_name': display_name,
                                      'email': email, 'phone': phone,
                                      'description': description}}
        else:
            put_query = {"apiVersion": 'v1alpha1',
                         'metadata': {'name': name,
                                      'display_name': display_name,
                                      'email': email, 'phone': phone,
                                      'description': description}}

        r = requests.put(
            ciconnect_api_endpoint + '/v1alpha1/groups/' + group_name, params=query, json=put_query)

        enclosing_group_name = '.'.join(group_name.split('.')[:-1])
        if r.status_code == requests.codes.ok:
            flash_message = flash_message_parser('edit_subgroup_requests')
            flash(flash_message, 'success')
            return redirect(url_for('users_groups_pending'))
        else:
            err_message = r.json()['message']
            flash('Failed to edit subgroup request: {}'.format(
                err_message), 'warning')
            return redirect(url_for('edit_subgroup_requests', group_name=group_name,
                                    name=name, display_name=display_name,
                                    email=email, phone=phone,
                                    description=description))


@app.route('/groups/<group_name>/edit', methods=['GET', 'POST'])
@authenticated
def edit_subgroup(group_name):
    access_token = get_user_access_token(session)
    query = {'token': access_token}
    if request.method == 'GET':
        sciences = requests.get(
            ciconnect_api_endpoint + '/v1alpha1/fields_of_science')
        sciences = sciences.json()['fields_of_science']
        group = get_group_info(group_name, session)
        return render_template('groups_edit.html', sciences=sciences,
                                group_name=group_name, group=group)

    elif request.method == 'POST':
        display_name = request.form['display-name']
        email = request.form['email']
        phone = request.form['phone']
        description = request.form['description']

        put_query = {"apiVersion": 'v1alpha1',
                     'metadata': {'display_name': display_name,
                                  'email': email, 'phone': phone,
                                  'description': description}}

        r = requests.put(
            ciconnect_api_endpoint + '/v1alpha1/groups/' + group_name, params=query, json=put_query)

        if r.status_code == requests.codes.ok:
            flash_message = flash_message_parser('edit_subgroup')
            flash(flash_message, 'success')
            return redirect(url_for('view_group', group_name=group_name))
        else:
            err_message = r.json()['message']
            flash('Failed to update subgroup information: {}'.format(
                err_message), 'warning')
            return redirect(url_for('edit_subgroup', group_name=group_name))


@app.route('/groups/<group_name>/subgroups/<subgroup_name>/approve', methods=['GET'])
@authenticated
def approve_subgroup(group_name, subgroup_name):
    access_token = get_user_access_token(session)
    query = {'token': access_token}
    if request.method == 'GET':

        r = requests.put(
            ciconnect_api_endpoint + '/v1alpha1/groups/' + group_name +
            '/subgroup_requests/' + subgroup_name + '/approve', params=query)

        if r.status_code == requests.codes.ok:
            flash_message = flash_message_parser('approve_subgroup')
            flash(flash_message, 'success')
            return redirect(url_for('view_group_subgroups_requests', group_name=group_name))
        else:
            err_message = r.json()['message']
            flash('Failed to approve subgroup creation: {}'.format(
                err_message), 'warning')
            return redirect(url_for('view_group_subgroups_requests', group_name=group_name))


@app.route('/groups/<group_name>/subgroups/<subgroup_name>/deny', methods=['POST'])
@authenticated
def deny_subgroup(group_name, subgroup_name):
    access_token = get_user_access_token(session)
    query = {'token': access_token}
    if request.method == 'POST':
        message = request.form['denial-message']
        denial_message = {'message': message}

        r = requests.delete(
            ciconnect_api_endpoint + '/v1alpha1/groups/' + group_name +
            '/subgroup_requests/' + subgroup_name, params=query, json=denial_message)

        if r.status_code == requests.codes.ok:
            flash_message = flash_message_parser('deny_subgroup')
            flash(flash_message, 'success')
            return redirect(url_for('view_group_subgroups_requests', group_name=group_name))
        else:
            err_message = r.json()['message']
            flash('Failed to deny subgroup request: {}'.format(
                err_message), 'warning')
            return redirect(url_for('view_group_subgroups_requests', group_name=group_name))


@app.route('/signup', methods=['GET'])
def signup():
    """Send the user to Globus Auth with signup=1."""
    domain_name = request.headers['Host']
    if 'usatlas' in domain_name:
        domain_name = 'atlas.ci-connect.net'
    elif 'uscms' in domain_name:
        domain_name = 'cms.ci-connect.net'
    elif 'uchicago' in domain_name:
        domain_name = 'psdconnect.uchicago.edu'

    with open(brand_dir + '/' + domain_name + '/signup_content/signup_modal.md', "r") as file:
        signup_modal_md = file.read()
    with open(brand_dir + '/' + domain_name + '/signup_content/signup_instructions.md', "r") as file:
        signup_instructions_md = file.read()
    with open(brand_dir + '/' + domain_name + '/signup_content/signup.md', "r") as file:
        signup_md = file.read()
    return render_template('signup.html', signup_modal_md=signup_modal_md, signup_instructions_md=signup_instructions_md, signup_md=signup_md)


@app.route('/aup', methods=['GET'])
def aup():
    """Send the user to Acceptable Use Policy page"""
    # Read AUP from markdown dir
    domain_name = request.headers['Host']
    if 'usatlas' in domain_name:
        domain_name = 'atlas.ci-connect.net'
    elif 'uscms' in domain_name:
        domain_name = 'cms.ci-connect.net'
    elif 'uchicago' in domain_name:
        domain_name = 'psdconnect.uchicago.edu'

    with open(brand_dir + '/' + domain_name + '/signup_content/signup_modal.md', "r") as file:
        aup_md = file.read()
    return render_template('AUP.html', aup_md=aup_md)


@app.route('/about', methods=['GET'])
def about():
    """Send the user to the About page"""
    # Read About from markdown dir
    domain_name = request.headers['Host']

    if 'usatlas' in domain_name:
        domain_name = 'atlas.ci-connect.net'
    elif 'uscms' in domain_name:
        domain_name = 'cms.ci-connect.net'
    elif 'uchicago' in domain_name:
        domain_name = 'psdconnect.uchicago.edu'

    with open(brand_dir + '/' + domain_name + '/about/about.md', "r") as file:
        about = file.read()
    
    organizations = [{'name': 'OSG',
                       'href': 'https://www.osgconnect.net',
                       'img': 'img/osg-org.png',
                       'description': "Member institutions of the the Open Science Grid are providing opportunistic CPU to support MC Taskforce simulations"},
                      {'name': 'PSD',
                       'href': 'https://psdconnect.uchicago.edu',
                       'img': 'img/psd-org.png',
                       'description': "The Physical Sciences Division is providing IT infrastructure supporting the login services and storage"},
                      {'name': 'SLATE',
                       'href': 'https://slateci.io/',
                       'img': 'img/slate-org.png',
                       'description': "The SLATE platform is utilized to assist in automating job submissions"},
                      {'name': 'MANIAC lab',
                       'href': 'https://maniaclab.uchicago.edu/',
                       'img': 'img/maniac-org.png',
                       'description': "Powered by MANIAC lab"}]
    return render_template('about.html', about=about, organizations=organizations)


@app.route('/login', methods=['GET'])
def login():
    """Send the user to Globus Auth."""
    return redirect(url_for('authcallback'))


@app.route('/logout', methods=['GET'])
@authenticated
def logout():
    """
    - Revoke the tokens with Globus Auth.
    - Destroy the session state.
    - Redirect the user to the Globus Auth logout page.
    """
    client = load_portal_client()

    # Revoke the tokens with Globus Auth
    for token, token_type in (
            (token_info[ty], ty)
            # get all of the token info dicts
            for token_info in session['tokens'].values()
            # cross product with the set of token types
            for ty in ('access_token', 'refresh_token')
            # only where the relevant token is actually present
            if token_info[ty] is not None):
        client.oauth2_revoke_token(
            token, additional_params={'token_type_hint': token_type})

    # Destroy the session state
    session.clear()

    redirect_uri = url_for('home', _external=True)

    ga_logout_url = []
    ga_logout_url.append(app.config['GLOBUS_AUTH_LOGOUT_URI'])
    ga_logout_url.append('?client={}'.format(app.config['PORTAL_CLIENT_ID']))
    ga_logout_url.append('&redirect_uri={}'.format(redirect_uri))
    ga_logout_url.append('&redirect_name=Connect Portal')

    # Redirect the user to the Globus Auth logout page
    return redirect(''.join(ga_logout_url))


@app.route('/profile/new', methods=['GET', 'POST'])
@authenticated
def create_profile():
    identity_id = session.get('primary_identity')
    institution = session.get('institution')
    globus_id = identity_id
    query = {'token': ciconnect_api_token}

    if request.method == 'GET':
        unix_name = ''
        phone = ''
        public_key = ''
        return render_template('profile_create.html', unix_name=unix_name, phone=phone, public_key=public_key)

    elif request.method == 'POST':
        name = request.form['name']
        unix_name = request.form['unix_name']
        email = request.form['email']
        phone = request.form['phone-number']
        institution = request.form['institution']
        public_key = request.form['sshpubstring']
        globus_id = session['primary_identity']
        superuser = False
        service_account = False

        # Schema and query for adding users to CI Connect DB
        if public_key:
            post_user = {"apiVersion": 'v1alpha1',
                         'metadata': {'globusID': globus_id, 'name': name, 'email': email,
                                      'phone': phone, 'institution': institution,
                                      'public_key': public_key,
                                      'unix_name': unix_name, 'superuser': superuser,
                                      'service_account': service_account}}
        else:
            post_user = {"apiVersion": 'v1alpha1',
                         'metadata': {'globusID': globus_id, 'name': name, 'email': email,
                                      'phone': phone, 'institution': institution,
                                      'unix_name': unix_name, 'superuser': superuser,
                                      'service_account': service_account}}
        r = requests.post(ciconnect_api_endpoint +
                          '/v1alpha1/users', params=query, json=post_user)
        # print("REQUEST RESPONSE: {}".format(r))
        # print("REQUEST URL: {}".format(r.url))
        if r.status_code == requests.codes.ok:
            r = r.json()['metadata']
            session['name'] = r['name']
            session['email'] = r['email']
            session['phone'] = r['phone']
            session['institution'] = r['institution']
            session['unix_name'] = r['unix_name']

            # Auto generate group membership into connect group
            put_query = {"apiVersion": 'v1alpha1',
                         'group_membership': {'state': 'pending'}}
            user_status = requests.put(
                ciconnect_api_endpoint +
                '/v1alpha1/groups/' +
                session['url_host']['unix_name'] + '/members/' + unix_name,
                params=query, json=put_query)

            flash_message = flash_message_parser('create_profile')
            flash(flash_message, 'success')

            # flash(
            #     'Account registration successful. A request for Unix account '
            #     + 'activation on the Connect job submission server has been '
            #     + 'forwarded to connect staff.', 'success')
            if 'next' in session:
                redirect_to = session['next']
                session.pop('next')
            else:
                redirect_to = url_for('profile')
            return redirect(url_for('profile'))
        else:
            error_msg = r.json()['message']
            flash(
                'Failed to create your account: {}'.format(error_msg), 'warning')
            return render_template('profile_create.html', name=name, unix_name=unix_name,
                                   email=email, phone=phone, institution=institution,
                                   public_key=public_key)


@app.route('/profile/edit/<unix_name>', methods=['GET', 'POST'])
@authenticated
def edit_profile(unix_name):
    identity_id = session.get('primary_identity')
    query = {'token': ciconnect_api_token,
             'globus_id': identity_id}
    user = requests.get(
        ciconnect_api_endpoint + '/v1alpha1/find_user', params=query)
    expected_unix_name = user.json()['metadata']['unix_name']

    try:
        unix_name == expected_unix_name
    except Exception:
        return redirect(url_for('handle_exception', e=Exception))

    if request.method == 'GET':
        # Get user info, pass through as args, convert to json and load input fields
        profile = requests.get(
            ciconnect_api_endpoint + '/v1alpha1/users/' + unix_name, params=query)
        profile = profile.json()['metadata']

        return render_template('profile_edit.html', profile=profile, unix_name=unix_name)

    elif request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone-number']
        institution = request.form['institution']
        public_key = request.form['sshpubstring']
        # print(request.form['csrf_token'])
        globus_id = session['primary_identity']
        access_token = get_user_access_token(session)
        query = {'token': access_token,
                 'globus_id': identity_id}
        # Schema and query for adding users to CI Connect DB
        if public_key != ' ':
            post_user = {"apiVersion": 'v1alpha1',
                         'metadata': {'name': name, 'email': email,
                                      'phone': phone, 'institution': institution,
                                      'public_key': public_key}}
        else:
            post_user = {"apiVersion": 'v1alpha1',
                         'metadata': {'name': name, 'email': email,
                                      'phone': phone, 'institution': institution}}
        # PUT request to update user information
        r = requests.put(ciconnect_api_endpoint + '/v1alpha1/users/' +
                         unix_name, params=query, json=post_user)

        session['name'] = name
        session['email'] = email
        session['phone'] = phone
        session['institution'] = institution

        flash_message = flash_message_parser('edit_profile')
        flash(flash_message, 'success')

        if 'next' in session:
            redirect_to = session['next']
            session.pop('next')
        else:
            redirect_to = url_for('profile')

        return redirect(url_for('profile'))


@app.route('/profile', methods=['GET', 'POST'])
@authenticated
def profile():
    """User profile information. Assocated with a Globus Auth identity."""
    if request.method == 'GET':
        identity_id = session.get('primary_identity')
        query = {'token': ciconnect_api_token,
                 'globus_id': identity_id}
        try:
            user = requests.get(ciconnect_api_endpoint +
                                '/v1alpha1/find_user', params=query)
            user = user.json()
            unix_name = user['metadata']['unix_name']

            profile = requests.get(
                ciconnect_api_endpoint + '/v1alpha1/users/' + unix_name, params=query)
            profile = profile.json()
        except:
            profile = None

        if profile:
            profile = profile['metadata']
            name = profile['name']
            email = profile['email']
            phone = profile['phone']
            institution = profile['institution']
            ssh_pubkey = profile['public_key']
            # Check User's Status in Specific Connect Group
            user_status = requests.get(ciconnect_api_endpoint + '/v1alpha1/users/' +
                                       profile['unix_name'] + '/groups/' + session['url_host']['unix_name'], params=query)
            user_status = user_status.json()['membership']['state']
        else:
            flash(
                'Please complete any missing profile fields and press Save.', 'warning')
            return redirect(url_for('create_profile'))

        if request.args.get('next'):
            session['next'] = get_safe_redirect()

        group_memberships = []
        for group in profile['group_memberships']:
            if ((session['url_host']['unix_name'] in group['name']) and (len(group['name'].split('.')) > 1)):
                group_memberships.append(group)

        domain_name = request.headers['Host']

        if 'usatlas' in domain_name:
            domain_name = 'atlas.ci-connect.net'
        elif 'uscms' in domain_name:
            domain_name = 'cms.ci-connect.net'
        elif 'uchicago' in domain_name:
            domain_name = 'psdconnect.uchicago.edu'

        with open(brand_dir + '/' + domain_name + "/form_descriptions/group_unix_name_description.md", "r") as file:
            group_unix_name_description = file.read()

        return render_template('profile.html', profile=profile,
                               user_status=user_status,
                               group_memberships=group_memberships,
                               group_unix_name_description=group_unix_name_description)

    elif request.method == 'POST':
        name = session['name'] = request.form['name']
        email = session['email'] = request.form['email']
        institution = session['institution'] = request.form['institution']
        globus_id = session['primary_identity']
        phone = request.form['phone-number']
        public_key = request.form['sshpubstring']
        superuser = True
        service_account = False

        # flash('Thank you! Your profile has been successfully updated.', 'success')

        if 'next' in session:
            redirect_to = session['next']
            session.pop('next')
        else:
            redirect_to = url_for('profile')

        return redirect(redirect_to)


@app.route('/authcallback', methods=['GET'])
def authcallback():
    """Handles the interaction with Globus Auth."""
    # If we're coming back from Globus Auth in an error state, the error
    # will be in the "error" query string parameter.
    if 'error' in request.args:
        flash("You could not be logged into the portal: " +
              request.args.get('error_description', request.args['error']), 'warning')
        return redirect(url_for('home'))

    # Set up our Globus Auth/OAuth2 state
    redirect_uri = url_for('authcallback', _external=True)

    client = load_portal_client()
    client.oauth2_start_flow(redirect_uri, refresh_tokens=True)

    # If there's no "code" query string parameter, we're in this route
    # starting a Globus Auth login flow.
    if 'code' not in request.args:
        additional_authorize_params = (
            {'signup': 1} if request.args.get('signup') else {})

        auth_uri = client.oauth2_get_authorize_url(
            additional_params=additional_authorize_params)

        return redirect(auth_uri)
    else:
        # If we do have a "code" param, we're coming back from Globus Auth
        # and can start the process of exchanging an auth code for a token.
        code = request.args.get('code')
        tokens = client.oauth2_exchange_code_for_tokens(code)

        id_token = tokens.decode_id_token(client)
        session.update(
            tokens=tokens.by_resource_server,
            is_authenticated=True,
            name=id_token.get('name', ''),
            email=id_token.get('email', ''),
            institution=id_token.get('organization', ''),
            primary_username=id_token.get('preferred_username'),
            primary_identity=id_token.get('sub'),
        )

        access_token = session['tokens']['auth.globus.org']['access_token']
        token_introspect = client.oauth2_token_introspect(
            token=access_token, include='identity_set')
        identity_set = token_introspect.data['identity_set']
        profile = None

        for identity in identity_set:
            query = {'token': ciconnect_api_token,
                     'globus_id': identity}
            try:
                r = requests.get(
                    ciconnect_api_endpoint + '/v1alpha1/find_user', params=query)
                if r.status_code == requests.codes.ok:
                    user_info = r.json()
                    # user_access_token = user_info['metadata']['access_token']
                    unix_name = user_info['metadata']['unix_name']
                    profile = requests.get(
                        ciconnect_api_endpoint + '/v1alpha1/users/' + unix_name, params=query)
                    profile = profile.json()
                    session['primary_identity'] = identity
            except:
                print("NOTHING HERE: {}".format(identity))

        connect_keynames = {'atlas': {'name': 'atlas-connect',
                                      'display_name': 'Atlas Connect',
                                      'unix_name': 'root.atlas'},
                            'cms': {'name': 'cms-connect',
                                    'display_name': 'CMS Connect',
                                    'unix_name': 'root.cms'},
                            'duke': {'name': 'duke-connect',
                                     'display_name': 'Duke Connect',
                                     'unix_name': 'root.duke'},
                            'uchicago': {'name': 'uchicago-connect',
                                         'display_name': 'UChicago Connect',
                                         'unix_name': 'root.uchicago'},
                            'spt': {'name': 'spt-connect',
                                    'display_name': 'SPT Connect',
                                    'unix_name': 'root.spt'},
                            'psdconnect': {'name': 'psd-connect',
                                           'display_name': 'PSD Connect',
                                           'unix_name': 'root.uchicago'},
                            'snowmass21': {'name': 'snowmass21-connect',
                                    'display_name': 'Snowmass21 Connect',
                                    'unix_name': 'root.snowmass21'},
                            'localhost': {'name': 'uchicago-connect',
                                          'display_name': 'UChicago Connect',
                                          'unix_name': 'root.uchicago'}}
        url_host = request.host
        if 'ci-connect' in url_host:
            session['url_host'] = {'name': 'ci-connect',
                                   'display_name': 'CI Connect',
                                   'unix_name': 'root'}

        for key, value in connect_keynames.iteritems():
            if key in url_host:
                session['url_host'] = value

        if profile:
            profile = profile['metadata']
            session['name'] = profile['name']
            session['email'] = profile['email']
            session['phone'] = profile['phone']
            session['institution'] = profile['institution']
            session['unix_name'] = profile['unix_name']
            session['url_root'] = request.url_root
            # session['url_host'] = (request.host).split(':')[0]
            session['admin'] = admin_check(profile['unix_name'])
        else:
            session['url_root'] = request.url_root
            return redirect(url_for('create_profile',
                                    next=url_for('profile')))
        return redirect(url_for('profile'))


def admin_check(unix_name):
    """
    Check user status on login, and set return admin status
    :param unix_name: unix name of user
    :return: user's status in Connect group
    """
    query = {'token': ciconnect_api_token}
    # Query to return user's membership status in a group specifically the root connect group
    r = requests.get(
        ciconnect_api_endpoint + '/v1alpha1/users/' + unix_name + '/groups/' + session['url_host']['unix_name'], params=query)
    user_status = r.json()['membership']['state']
    return user_status
