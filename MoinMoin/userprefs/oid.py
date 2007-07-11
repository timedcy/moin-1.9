# -*- coding: iso-8859-1 -*-
"""
    MoinMoin - OpenID preferences

    @copyright: 2007     MoinMoin:JohannesBerg
    @license: GNU GPL, see COPYING for details.
"""

from MoinMoin import wikiutil
from MoinMoin.widget import html
from MoinMoin.userprefs import UserPrefBase
from MoinMoin.auth.openidrp import OpenIDAuth
import sha
from MoinMoin.util.moinoid import MoinOpenIDStore
from openid.consumer import consumer
from openid.yadis.discover import DiscoveryFailure
from openid.fetchers import HTTPFetchingError


class Settings(UserPrefBase):
    def __init__(self, request):
        """ Initialize OpenID settings form. """
        UserPrefBase.__init__(self, request)
        self.request = request
        self._ = request.getText
        self.cfg = request.cfg
        self.title = self._("OpenID settings")

    def allowed(self):
        for authm in self.request.cfg.auth:
            if isinstance(authm, OpenIDAuth):
                return UserPrefBase.allowed(self)
        return False

    def _handle_remove(self):
        _ = self.request.getText
        openids = self.request.user.openids[:]
        for oid in self.request.user.openids:
            name = "rm-%s" % sha.new(oid).hexdigest()
            if name in self.request.form:
                openids.remove(oid)
        if not openids and len(self.request.cfg.auth) == 1:
            return _("Cannot remove all OpenIDs.")
        self.request.user.openids = openids
        self.request.user.save()
        return _("The selected OpenIDs have been removed.")

    def _handle_add(self):
        _ = self.request.getText
        request = self.request

        openid_id = request.form.get('openid_identifier', [''])[0]

        if openid_id in request.user.openids:
            return _("OpenID is already present.")

        oidconsumer = consumer.Consumer(request.session,
                                        MoinOpenIDStore(self.request))
        try:
            oidreq = oidconsumer.begin(openid_id)
        except HTTPFetchingError:
            return _('Failed to resolve OpenID.')
        except DiscoveryFailure:
            return _('OpenID discovery failure, not a valid OpenID.')
        else:
            if oidreq is None:
                return _("No OpenID.")

            qstr = wikiutil.makeQueryString({'action': 'userprefs',
                                             'handler': 'oid',
                                             'oid.return': '1'})
            return_to = '%s/%s' % (request.getBaseURL(),
                                   request.page.url(request, qstr))
            trust_root = request.getBaseURL()
            if oidreq.shouldSendRedirect():
                redirect_url = oidreq.redirectURL(trust_root, return_to)
                request.http_redirect(redirect_url)
            else:
                form_html = oidreq.formMarkup(trust_root, return_to,
                    form_tag_attrs={'id': 'openid_message'})
                request.session['openid.prefs.form_html'] = form_html


    def _handle_oidreturn(self):
        request = self.request
        _ = request.getText

        oidconsumer = consumer.Consumer(request.session,
                                        MoinOpenIDStore(request))
        query = {}
        for key in request.form:
            query[key] = request.form[key][0]
        qstr = wikiutil.makeQueryString({'action': 'userprefs',
                                         'handler': 'oid',
                                         'oid.return': '1'})
        return_to = '%s/%s' % (request.getBaseURL(),
                               request.page.url(request, qstr))
        info = oidconsumer.complete(query, return_to=return_to)
        if info.status == consumer.FAILURE:
            return _('OpenID error: %s.') % info.message
        elif info.status == consumer.CANCEL:
            return _('Verification canceled.')
        elif info.status == consumer.SUCCESS:
            if not info.identity_url in request.user.openids:
                request.user.openids.append(info.identity_url)
                request.user.save()
                return _("OpenID added successfully.")
            else:
                return _("OpenID is already present.")
        else:
            return _('OpenID failure.')


    def handle_form(self):
        _ = self._
        form = self.request.form

        if form.has_key('oid.return'):
            return self._handle_oidreturn()

        if form.has_key('cancel'):
            return

        if form.has_key('remove'):
            return self._handle_remove()

        if form.has_key('add'):
            return self._handle_add()

        return

    def _make_form(self):
        sn = self.request.getScriptname()
        pi = self.request.getPathinfo()
        action = u"%s%s" % (sn, pi)
        _form = html.FORM(action=action)
        _form.append(html.INPUT(type="hidden", name="action", value="userprefs"))
        _form.append(html.INPUT(type="hidden", name="handler", value="oid"))
        return _form

    def _make_row(self, label, cell, **kw):
        """ Create a row in the form table.
        """
        self._table.append(html.TR().extend([
            html.TD(**kw).extend([html.B().append(label), '   ']),
            html.TD().extend(cell),
        ]))

    def _oidlist(self):
        _ = self.request.getText
        form = self._make_form()
        for oid in self.request.user.openids:
            name = "rm-%s" % sha.new(oid).hexdigest()
            form.append(html.INPUT(type="checkbox", name=name, id=name))
            form.append(html.LABEL(for_=name).append(html.Text(oid)))
            form.append(html.BR())
        self._make_row(_("Current OpenIDs"), [form], valign='top')
        label = _("Remove selected")
        form.append(html.BR())
        form.append(html.INPUT(type="submit", name="remove", value=label))

    def _addoidform(self):
        _ = self.request.getText
        form = self._make_form()
        # go back to this page
        form.append(html.INPUT(type="hidden", name="sub", value="oid"))
        label = _("Add OpenID")
        form.append(html.INPUT(type="text", size="32",
                               name="openid_identifier",
                               id="openididentifier"))
        form.append(html.BR())
        form.append(html.INPUT(type="submit", name="add", value=label))
        self._make_row(_('Add OpenID'), [form])

    def create_form(self):
        """ Create the complete HTML form code. """
        _ = self._

        ret = html.P()
        # Use the user interface language and direction
        lang_attr = self.request.theme.ui_lang_attr()
        ret.append(html.Raw('<div %s>' % lang_attr))
        self._table = html.TABLE(border="0")
        ret.append(self._table)
        ret.append(html.Raw("</div>"))

        request = self.request

        if 'openid.prefs.form_html' in request.session:
            txt = _('OpenID verification requires that you click this button:')
            # create JS to automatically submit the form if possible
            submitjs = """<script type="text/javascript">
<!--//
document.getElementById("openid_message").submit();
//-->
</script>
"""
            oidhtml = request.session['openid.prefs.form_html']
            del request.session['openid.prefs.form_html']
            return ''.join([txt, oidhtml, submitjs])

        if request.user.openids:
            self._oidlist()
        self._addoidform()

        form = self._make_form()
        label = _("Cancel")
        form.append(html.INPUT(type="submit", name='cancel', value=label))
        self._make_row('', [form])
        return unicode(ret)
