#coding: utf-8
# +-------------------------------------------------------------------
# | 宝塔Linux面板 
# +-------------------------------------------------------------------
# | Copyright (c) 2015-2099 宝塔软件(http://bt.cn) All rights reserved.
# +-------------------------------------------------------------------
# | Author: hwliang <hwl@bt.cn>
# +-------------------------------------------------------------------
import sys
import json
import os
import time
import re
import uuid
import threading
os.chdir('/www/server/panel/')
sys.path.insert(0,'class/')
import public
from flask import Flask,current_app,session,render_template,send_file,request,redirect,g,url_for,make_response,render_template_string,abort
from flask_session import Session

try:
    from werkzeug.contrib.cache import SimpleCache
except:
    from cachelib import SimpleCache

from werkzeug.wrappers import Response
from flask_sockets import Sockets
sys.setrecursionlimit(1000000)
cache = SimpleCache()
from flask_compress import Compress
app = Flask(__name__,template_folder="templates/" + public.GetConfigValue('template'))
Compress(app)
sockets = Sockets(app)


import common
import db
import jobs

dns_client = None
app.config['DEBUG'] = os.path.exists('data/debug.pl')

#设置BasicAuth
basic_auth_conf = 'config/basic_auth.json'
app.config['BASIC_AUTH_OPEN'] = False
if os.path.exists(basic_auth_conf):
    try:
        ba_conf = json.loads(public.readFile(basic_auth_conf))
        app.config['BASIC_AUTH_USERNAME'] = ba_conf['basic_user']
        app.config['BASIC_AUTH_PASSWORD'] = ba_conf['basic_pwd']
        app.config['BASIC_AUTH_OPEN'] = ba_conf['open']
    except: pass


job = threading.Thread(target=jobs.control_init)
job.setDaemon(True)
job.start()

app.secret_key = uuid.UUID(int=uuid.getnode()).hex[-12:]
local_ip = None
my_terms = {}
sdb = None
try:
    from flask_sqlalchemy import SQLAlchemy
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////dev/shm/session.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = True
    sdb = SQLAlchemy(app)
    app.config['SESSION_TYPE'] = 'sqlalchemy'
    app.config['SESSION_SQLALCHEMY'] = sdb
    app.config['SESSION_SQLALCHEMY_TABLE'] = 'session'
    s_sqlite = True
except:
    app.config['SESSION_TYPE'] = 'filesystem'
    app.config['SESSION_FILE_DIR'] = r'/dev/shm/session_py' + str(sys.version_info[0])
    app.config['SESSION_FILE_THRESHOLD'] = 2048
    app.config['SESSION_FILE_MODE'] = 384
    s_sqlite = False
    public.ExecShell("pip install flask_sqlalchemy &")

app.config['SESSION_PERMANENT'] = True
app.config['SESSION_USE_SIGNER'] = True
app.config['SESSION_KEY_PREFIX'] = 'BT_:'
app.config['SESSION_COOKIE_NAME'] = "BT_PANEL_6"
app.config['PERMANENT_SESSION_LIFETIME'] = 86400
Session(app)


if s_sqlite:
    sdb.create_all()
    public.ExecShell("chmod 600 /dev/shm/session.db")

from datetime import datetime
import socket

comm = common.panelAdmin()
method_all = ['GET','POST']
method_get = ['GET']
method_post = ['POST']
json_header = {'Content-Type':'application/json; charset=utf-8'}
cache.set('p_token','bmac_' + public.Md5(public.get_mac_address()))
admin_path_file = 'data/admin_path.pl'
admin_path = '/'
if os.path.exists(admin_path_file): admin_path = public.readFile(admin_path_file).strip()
admin_path_checks = [
                    '/',
                    '/san',
                    '/bak',
                    '/monitor',
                    '/abnormal',
                    '/close',
                    '/task',
                    '/login',
                    '/config',
                    '/site',
                    '/sites',
                    '/ftp',
                    '/public',
                    '/database',
                    '/data',
                    '/download_file',
                    '/control',
                    '/crontab',
                    '/firewall',
                    '/files',
                    '/soft',
                    '/ajax',
                    '/system',
                    '/panel_data',
                    '/code',
                    '/ssl',
                    '/plugin',
                    '/wxapp',
                    '/hook',
                    '/safe',
                    '/yield',
                    '/downloadApi',
                    '/pluginApi',
                    '/auth',
                    '/download',
                    '/cloud',
                    '/webssh',
                    '/connect_event',
                    '/panel',
                    '/acme',
                    '/down',
                    '/api',
                    '/tips',
                    '/message'
                    ]
if admin_path in admin_path_checks: admin_path = '/bt'

@app.route('/service_status',methods = method_get)
def service_status():
    return 'True'

@sockets.route('/webssh')
def webssh(ws):
    if not check_login():
        session.clear()
        ws.send('server_response',"Panel session is lost, please re-login panel!")
        return None
    if not 'ssh_obj' in session:
        import ssh_terminal
        session['ssh_obj'] = ssh_terminal.ssh_terminal()
    if not 'ssh_info' in session:
        s_file = '/www/server/panel/config/t_info.json'
        if os.path.exists(s_file):
            try:
                session['ssh_info'] = json.loads(public.en_hexb(public.readFile(s_file)))
            except:
                session['ssh_info'] = {"host":"127.0.0.1","port":22}
        else:
            session['ssh_info'] = {"host":"127.0.0.1","port":22}

    session['ssh_obj'].run(ws,session['ssh_info'])


@app.route('/term_open',methods=method_all)
def term_open():
    comReturn = comm.local()
    if comReturn: return comReturn
    args = get_input()
    if 'get_ssh_info' in args:
        key = 'ssh_' + args['host']
        if key in session:
            return public.getJson(session[key]),json_header
        return public.returnMsg(False,'Acquisition failed!')
    session['ssh_info'] = json.loads(args.data)
    key = 'ssh_' + session['ssh_info']['host']
    session[key] = session['ssh_info']
    s_file = '/www/server/panel/config/t_info.json'
    if 'is_save' in session['ssh_info']:
        public.writeFile(s_file,public.de_hexb(json.dumps(session['ssh_info'])),'wb+')
        public.set_mode(s_file,600)
    else:
        if os.path.exists(s_file): os.remove(s_file)
    if 'ssh_obj' in session: session['ssh_obj']._ssh_info = session['ssh_info']
    return public.returnJson(True,'Successful setup!')

@app.route('/reload_mod',methods=method_all)
def reload_mod():
    comReturn = comm.local()
    if comReturn: return comReturn
    args = get_input()
    mod_name = None
    if 'mod_name' in args:
        mod_name = args.mod_name
    result = public.reload_mod(mod_name)
    if result: return public.returnJson(True,result),json_header
    return public.returnJson(False,'Reload failure!'),json_header

@app.before_request
def request_check():
    #if not public.path_safe_check(request.path): return abort(404)
    if request.path in ['/service_status']: return

    if not request.path in ['/safe','/hook','/public','/mail_sys','/down']:
        ip_check = public.check_ip_panel()
        if ip_check: return ip_check

    if request.path.find('/static/') != -1 or request.path == '/code':
        if not 'login' in session and not 'admin_auth' in session and not 'down' in session:
            session.clear()
            return abort(401)
    domain_check = public.check_domain_panel()
    if domain_check: return domain_check
    if public.is_local():
        not_networks = ['uninstall_plugin','install_plugin','UpdatePanel']
        if request.args.get('action') in not_networks: 
            return public.returnJson(False,'This feature is not available in offline mode!'),json_header

    if app.config['BASIC_AUTH_OPEN']:
        if request.path in ['/public','/download','/mail_sys','/hook','/down','/check_bind','/get_app_bind_status']: return
        auth = request.authorization
        if not comm.get_sk(): return
        if not auth: return send_authenticated()
        tips = '_bt.cn'
        if public.md5(auth.username.strip() + tips) != app.config['BASIC_AUTH_USERNAME'] \
            or public.md5(auth.password.strip() + tips) != app.config['BASIC_AUTH_PASSWORD']:
            return send_authenticated()

@app.teardown_request
def request_end(reques = None):
    not_acts = ['GetTaskSpeed','GetNetWork','check_pay_status','get_re_order_status','get_order_stat']
    key = request.args.get('action')
    if not key in not_acts and request.full_path.find('/static/') == -1: public.write_request_log()

def send_authenticated():
    global local_ip
    if not local_ip: local_ip = public.GetLocalIp()
    result = Response('', 401,{'WWW-Authenticate': 'Basic realm="%s"' % local_ip.strip()})
    if not 'login' in session and not 'admin_auth' in session: session.clear()
    return result

@app.route('/',methods=method_all)
def home():
    comReturn = comm.local()
    if comReturn: return comReturn
    data = {}
    data[public.to_string([112, 100])],data['pro_end'],data['ltd_end'] = get_pd()
    data['siteCount'] = public.M('sites').count()
    data['ftpCount'] = public.M('ftps').count()
    data['databaseCount'] = public.M('databases').count()
    data['lan'] = public.GetLan('index')
    data['724'] = public.format_date("%m%d") == '0724'
    public.auto_backup_panel()
    return render_template( 'index.html',data = data)

@app.route('/close',methods=method_get)
def close():
    if not os.path.exists('data/close.pl'): return redirect('/')
    data = {}
    data['lan'] = public.getLan('close')
    return render_template('close.html',data=data)

@app.route('/tips',methods=method_get)
def tips():
    return render_template('tips.html')


route_path = os.path.join(admin_path,'')
if route_path[-1] == '/': route_path = route_path[:-1]
if route_path[0] != '/': route_path = '/' + route_path
@app.route('/login',methods=method_all)
@app.route(route_path,methods=method_all)
@app.route(route_path + '/',methods=method_all)
def login():
    if os.path.exists('install.pl'): return redirect('/install')
    global admin_check_auth,admin_path,route_path
    is_auth_path = False
    if admin_path != '/bt' and os.path.exists(admin_path_file) and  not 'admin_auth' in session:
        is_auth_path = True
    get = get_input()
    import userlogin
    if hasattr(get,'tmp_token'):
        result = userlogin.userlogin().request_tmp(get)
        return is_login(result)

    if hasattr(get,'dologin'):
        login_path = '/login'
        if not 'login' in session: return redirect(login_path)
        if os.path.exists(admin_path_file): login_path = route_path
        if session['login'] != False:
            session['login'] = False
            cache.set('dologin',True)
            session.clear()
            session_path = r'/dev/shm/session_py' + str(sys.version_info[0])
            if os.path.exists(session_path): public.ExecShell("rm -f " + session_path + '/*')
            return redirect(login_path)
    
    if is_auth_path:
        if route_path != request.path and route_path + '/' != request.path:
            data = {}
            data['lan'] = public.getLan('close')
            return render_template('autherr.html',data=data)
    session['admin_auth'] = True
    comReturn = common.panelSetup().init()
    if comReturn: return comReturn

    if request.method == method_post[0]:
        result = userlogin.userlogin().request_post(get)
        if result == "1":
            return result
        return is_login(result)

    if request.method == method_get[0]:
        result = userlogin.userlogin().request_get(get)
        if result: return result
        data = {}
        data['lan'] = public.GetLan('login')
        data['hosts'] = '[]'
        hosts_file = 'plugin/static_cdn/hosts.json'
        if os.path.exists(hosts_file):
            data['hosts'] = public.get_cdn_hosts()
            if type(data['hosts']) == dict:
                data['hosts'] = '[]'
            else:
                data['hosts'] = json.dumps(data['hosts'])
        return render_template(
            'login.html',
            data=data
            )

def is_login(result):
    if 'login' in session:
        if session['login'] == True:
            result = make_response(result)
            request_token = public.GetRandomString(48)
            session['request_token'] = request_token
            result.set_cookie('request_token',request_token,max_age=86400*30)
    return result

@app.route('/site',methods=method_all)
def site(pdata = None):
    comReturn = comm.local()
    if comReturn: return comReturn
    if request.method == method_get[0] and not pdata:
        data = {}
        data['isSetup'] = True
        data['lan'] = public.getLan('site')
        if os.path.exists(public.GetConfigValue('setup_path')+'/nginx') == False \
            and os.path.exists(public.GetConfigValue('setup_path')+'/apache') == False \
                and os.path.exists(public.GetConfigValue('openlitespeed_path')+'/lsws') == False:
            data['isSetup'] = False
        return render_template( 'site.html',data=data)
    import panelSite
    siteObject = panelSite.panelSite()
        
    defs = ('get_site_domains','GetRedirectFile','SaveRedirectFile','DeleteRedirect','GetRedirectList','CreateRedirect','ModifyRedirect',
            'set_dir_auth','delete_dir_auth','get_dir_auth','modify_dir_auth_pass',
            'GetSiteLogs','GetSiteDomains','GetSecurity','SetSecurity','ProxyCache','CloseToHttps','HttpToHttps','SetEdate',
            'SetRewriteTel','GetCheckSafe','CheckSafe','GetDefaultSite','SetDefaultSite','CloseTomcat','SetTomcat','apacheAddPort',
            'AddSite','GetPHPVersion','SetPHPVersion','DeleteSite','AddDomain','DelDomain','GetDirBinding','AddDirBinding','GetDirRewrite',
            'DelDirBinding','get_site_types','add_site_type','remove_site_type','modify_site_type_name','set_site_type','UpdateRulelist',
            'SetSiteRunPath','GetSiteRunPath','SetPath','SetIndex','GetIndex','GetDirUserINI','SetDirUserINI','GetRewriteList','SetSSL',
            'SetSSLConf','CreateLet','CloseSSLConf','GetSSL','SiteStart','SiteStop','Set301Status','Get301Status','CloseLimitNet','SetLimitNet',
            'GetLimitNet','RemoveProxy','GetProxyList','GetProxyDetals','CreateProxy','ModifyProxy','GetProxyFile','SaveProxyFile','ToBackup',
            'DelBackup','GetSitePHPVersion','logsOpen','GetLogsStatus','CloseHasPwd','SetHasPwd','GetHasPwd','GetDnsApi','SetDnsApi')
    return publicObject(siteObject,defs,None,pdata)

@app.route('/ftp',methods=method_all)
def ftp(pdata = None):
    comReturn = comm.local()
    if comReturn: return comReturn
    if request.method == method_get[0] and not pdata:
        FtpPort()
        data = {}
        data['isSetup'] = True
        if os.path.exists(public.GetConfigValue('setup_path') + '/pure-ftpd') == False: data['isSetup'] = False
        data['lan'] = public.GetLan('ftp')
        return render_template('ftp.html',data=data)
    import ftp
    ftpObject = ftp.ftp()
    defs = ('AddUser','DeleteUser','SetUserPassword','SetStatus','setPort')
    return publicObject(ftpObject,defs,None,pdata)

#取端口
def FtpPort():
    if session.get('port'):return
    import re
    try:
        file = public.GetConfigValue('setup_path')+'/pure-ftpd/etc/pure-ftpd.conf'
        conf = public.readFile(file)
        rep = r"\n#?\s*Bind\s+[0-9]+\.[0-9]+\.[0-9]+\.+[0-9]+,([0-9]+)"
        port = re.search(rep,conf).groups()[0]
    except:
        port='21'
    session['port'] = port

@app.route('/database',methods=method_all)
def database(pdata = None):
    comReturn = comm.local()
    if comReturn: return comReturn
    if request.method == method_get[0] and not pdata:
        import ajax
        pmd = get_phpmyadmin_dir()
        session['phpmyadminDir'] = False
        if pmd: 
            session['phpmyadminDir'] = 'http://' + public.GetHost() + ':'+ pmd[1] + '/' + pmd[0]
        ajax.ajax().set_phpmyadmin_session()
        data = {}
        data['isSetup'] = os.path.exists(public.GetConfigValue('setup_path') + '/mysql/bin')
        data['mysql_root'] = public.M('config').where('id=?',(1,)).getField('mysql_root')
        data['lan'] = public.GetLan('database')
        return render_template('database.html',data=data)
    import database
    databaseObject = database.database()
    defs = ('check_mysql_ssl_status','write_ssl_to_mysql','GetdataInfo','GetInfo','ReTable','OpTable','AlTable','GetSlowLogs','GetRunStatus',
            'SetDbConf','GetDbStatus','BinLog','GetErrorLog','GetMySQLInfo','SetDataDir','SetMySQLPort',
            'AddDatabase','DeleteDatabase','SetupPassword','ResDatabasePassword','ToBackup','DelBackup',
            'InputSql','SyncToDatabases','SyncGetDatabases','GetDatabaseAccess','SetDatabaseAccess')
    return publicObject(databaseObject,defs,None,pdata)

def get_phpmyadmin_dir():
        path = public.GetConfigValue('setup_path') + '/phpmyadmin'
        if not os.path.exists(path): return None
        
        phpport = '888'
        try:
            import re;
            if session['webserver'] == 'nginx':
                filename =public.GetConfigValue('setup_path') + '/nginx/conf/nginx.conf'
                conf = public.readFile(filename)
                rep = "listen\s+([0-9]+)\s*;"
                rtmp = re.search(rep,conf)
                if rtmp:
                    phpport = rtmp.groups()[0]
            else:
                filename = public.GetConfigValue('setup_path') + '/apache/conf/extra/httpd-vhosts.conf'
                conf = public.readFile(filename)
                rep = "Listen\s+([0-9]+)\s*\n"
                rtmp = re.search(rep,conf)
                if rtmp:
                    phpport = rtmp.groups()[0]
        except:
            pass
            
        for filename in os.listdir(path):
            filepath = path + '/' + filename
            if os.path.isdir(filepath):
                if filename[0:10] == 'phpmyadmin':
                    return str(filename),phpport
        return None

@app.route('/acme',methods=method_all)
def acme(pdata = None):
    comReturn = comm.local()
    if comReturn: return comReturn
    import acme_v2
    acme_v2_object = acme_v2.acme_v2()
    defs = ('get_orders','remove_order','get_order_find','revoke_order','create_order','get_account_info','set_account_info','update_zip','get_cert_init_api',
            'get_auths','auth_domain','check_auth_status','download_cert','apply_cert','renew_cert','apply_cert_api','apply_dns_auth')
    return publicObject(acme_v2_object,defs,None,pdata)

@app.route('/message/<action>',methods=method_all)
def message(action = None):
    comReturn = comm.local()
    if comReturn: return comReturn
    import panelMessage
    message_object = panelMessage.panelMessage()
    defs = ('get_messages','get_message_find','create_message','status_message','remove_message','get_messages_all')
    return publicObject(message_object,defs,action,None)

@app.route('/api',methods=method_all)
def api(pdata = None):
    comReturn = comm.local()
    if comReturn: return comReturn
    import panelApi
    api_object = panelApi.panelApi()
    defs = ('get_token','check_bind','get_bind_status','get_apps','add_bind_app','remove_bind_app','set_token','get_tmp_token','get_app_bind_status')
    return publicObject(api_object,defs,None,pdata)

@app.route('/get_app_bind_status',methods=method_all)
def get_app_bind_status(pdata = None):
    import panelApi
    api_object = panelApi.panelApi()
    return json.dumps(api_object.get_app_bind_status(get_input())),json_header

@app.route('/check_bind',methods=method_all)
def check_bind(pdata = None):
    import panelApi
    api_object = panelApi.panelApi()
    return json.dumps(api_object.check_bind(get_input())),json_header

@app.route('/control',methods=method_all)
def control(pdata = None):
    comReturn = comm.local()
    if comReturn: return comReturn
    if request.method == method_get[0]:
        data = {}
        data['lan'] = public.GetLan('control')
        return render_template( 'control.html',data=data)

@app.route('/firewall',methods=method_all)
def firewall(pdata = None):
    comReturn = comm.local()
    if comReturn: return comReturn
    if request.method == method_get[0] and not pdata:
        data = {}
        data['lan'] = public.GetLan('firewall')
        return render_template( 'firewall.html',data=data)
    import firewalls
    firewallObject = firewalls.firewalls()
    defs = ('GetList','AddDropAddress','DelDropAddress','FirewallReload','SetFirewallStatus',
            'AddAcceptPort','DelAcceptPort','SetSshStatus','SetPing','SetSshPort','GetSshInfo')
    return publicObject(firewallObject,defs,None,pdata)

@app.route('/ssh_security',methods=method_all)
def ssh_security(pdata = None):
    comReturn = comm.local()
    if comReturn: return comReturn
    if request.method == method_get[0] and not pdata:
        data = {}
        data['lan'] = public.GetLan('firewall')
        return render_template( 'firewall.html',data=data)
    import ssh_security
    firewallObject = ssh_security.ssh_security()
    defs = ('san_ssh_security','set_password','set_sshkey','stop_key','get_config',
            'stop_password','get_key','return_ip','add_return_ip','del_return_ip','start_jian','stop_jian','get_jian','get_logs')
    return publicObject(firewallObject,defs,None,pdata)


@app.route('/firewall_new',methods=method_all)
def firewall_new(pdata = None):
    comReturn = comm.local()
    if comReturn: return comReturn
    if request.method == method_get[0] and not pdata:
        data = {}
        data['lan'] = public.GetLan('firewall')
        return render_template( 'firewall_new.html',data=data)
    import firewall_new
    firewallObject = firewall_new.firewalls()
    defs = ('GetList','AddDropAddress','DelDropAddress','FirewallReload','SetFirewallStatus',
            'AddAcceptPort','DelAcceptPort','SetSshStatus','SetPing','SetSshPort','GetSshInfo',
            'AddSpecifiesIp','DelSpecifiesIp'
            )
    return publicObject(firewallObject,defs,None,pdata)


@app.route('/monitor', methods=method_all)
def panel_monitor(pdata=None):
    comReturn = comm.local()
    if comReturn: return comReturn
    import monitor
    dataObject = monitor.Monitor()
    defs = ('get_spider', 'get_exception', 'get_request_count_qps', 'load_and_up_flow', 'get_request_count_by_hour')
    return publicObject(dataObject, defs, None, pdata)


@app.route('/san', methods=method_all)
def san_baseline(pdata=None):
    comReturn = comm.local()
    if comReturn: return comReturn
    import san_baseline
    dataObject = san_baseline.san_baseline()
    defs = ('start', 'get_api_log', 'get_resut', 'get_ssh_errorlogin','repair','repair_all')
    return publicObject(dataObject, defs, None, pdata)

@app.route('/password', methods=method_all)
def panel_password(pdata=None):
    comReturn = comm.local()
    if comReturn: return comReturn
    import password
    dataObject = password.password()
    defs = ('set_root_password', 'get_mysql_root', 'set_mysql_password', 'set_panel_password',
            'SetPassword', 'SetSshKey','StopKey','GetConfig','StopPassword','GetKey',
            'get_databses','rem_mysql_pass','set_mysql_access',"get_panel_username"
            )
    return publicObject(dataObject, defs, None, pdata)


@app.route('/bak', methods=method_all)
def backup_bak(pdata=None):
    comReturn = comm.local()
    if comReturn: return comReturn
    import backup_bak
    dataObject = backup_bak.backup_bak()
    defs = ('get_sites', 'get_databases', 'backup_database', 'backup_site', 'backup_path', 'get_database_progress',
            'get_site_progress', 'down','get_down_progress','download_path','backup_site_all','get_all_site_progress',
            'backup_date_all','get_all_date_progress'
            )
    return publicObject(dataObject, defs, None, pdata)


@app.route('/abnormal', methods=method_all)
def abnormal(pdata=None):
    comReturn = comm.local()
    if comReturn: return comReturn
    import abnormal
    dataObject = abnormal.abnormal()
    defs = ('mysql_server', 'mysql_cpu', 'mysql_count', 'php_server', 'php_conn_max',
            'php_cpu', 'CPU', 'Memory', 'disk', 'not_root_user', 'start'
            )
    return publicObject(dataObject, defs, None, pdata)

@app.route('/files',methods=method_all)
def files(pdata = None):
    comReturn = comm.local()
    if comReturn: return comReturn
    if request.method == method_get[0] and not request.args.get('path') and not pdata:
        data = {}
        data['lan'] = public.GetLan('files')
        return render_template('files.html',data=data)
    import files
    filesObject = files.files()
    defs = ('fix_permissions','get_all_back','restore_path_permissions','del_path_premissions','get_path_premissions','back_path_permissions',
            'CheckExistsFiles','GetExecLog','GetSearch','ExecShell','GetExecShellMsg','exec_git','exec_composer','create_download_url',
            'UploadFile','GetDir','CreateFile','CreateDir','DeleteDir','DeleteFile','get_download_url_list','remove_download_url','modify_download_url',
            'CopyFile','CopyDir','MvFile','GetFileBody','SaveFileBody','Zip','UnZip','get_download_url_find',
            'SearchFiles','upload','read_history','re_history','auto_save_temp','get_auto_save_body','get_videos',
            'GetFileAccess','SetFileAccess','GetDirSize','SetBatchData','BatchPaste','install_rar','get_path_size',
            'DownloadFile','GetTaskSpeed','CloseLogs','InstallSoft','UninstallSoft','SaveTmpFile','get_composer_version','exec_composer','update_composer',
            'GetTmpFile','del_files_store','add_files_store','get_files_store','del_files_store_types','add_files_store_types','exec_git',
            'RemoveTask','ActionTask','Re_Recycle_bin','Get_Recycle_bin','Del_Recycle_bin','Close_Recycle_bin','Recycle_bin','file_webshell_check','dir_webshell_check'
            )
    return publicObject(filesObject,defs,None,pdata)


@app.route('/crontab',methods=method_all)
def crontab(pdata = None):
    comReturn = comm.local()
    if comReturn: return comReturn
    if request.method == method_get[0] and not pdata:
        data = {}
        data['lan'] = public.GetLan('crontab')
        return render_template( 'crontab.html',data=data)
    import crontab
    crontabObject = crontab.crontab()
    defs = ('GetCrontab','AddCrontab','GetDataList','GetLogs','DelLogs','DelCrontab',
            'StartTask','set_cron_status','get_crond_find','modify_crond'
            )
    return publicObject(crontabObject,defs,None,pdata)

@app.route('/soft',methods=method_all)
def soft(pdata = None):
    comReturn = comm.local()
    if comReturn: return comReturn
    if request.method == method_get[0] and not pdata:
        data={}
        data['lan'] = public.GetLan('soft')
        return render_template( 'soft.html',data=data)

@app.route('/config',methods=method_all)
def config(pdata = None):
    comReturn = comm.local()
    if comReturn: return comReturn
    if request.method == method_get[0] and not pdata:
        import system,wxapp,config
        c_obj = config.config()
        data = system.system().GetConcifInfo()
        data['lan'] = public.GetLan('config')
        try:
            data['wx'] = wxapp.wxapp().get_user_info(None)['msg']
        except:
            data['wx'] = 'INIT_WX_NOT_BIND'
        data['api'] = ''
        data['ipv6'] = ''
        sess_out_path = 'data/session_timeout.pl'
        if not os.path.exists(sess_out_path): public.writeFile(sess_out_path,'86400')
        workers_p = 'data/workers.pl'
        if not os.path.exists(workers_p): public.writeFile(workers_p,'1')
        data['workers'] = int(public.readFile(workers_p))
        s_time_tmp = public.readFile(sess_out_path)
        if not s_time_tmp: s_time_tmp = '0'
        data['session_timeout'] = int(s_time_tmp)
        if c_obj.get_ipv6_listen(None): data['ipv6'] = 'checked'
        if c_obj.get_token(None)['open']: data['api'] = 'checked'
        data['basic_auth'] = c_obj.get_basic_auth_stat(None)
        data['basic_auth']['value'] = public.GetMsg("CLOSE")
        if data['basic_auth']['open']: data['basic_auth']['value'] = public.GetMsg("OPEN")
        data['debug'] = ''
        if app.config['DEBUG']: data['debug'] = 'checked'
        data['is_local'] = ''
        if public.is_local(): data['is_local'] = 'checked'
        return render_template( 'config.html',data=data)
    import config
    defs = ('get_ols_private_cache_status','get_ols_value','set_ols_value','get_ols_private_cache','get_ols_static_cache','set_ols_static_cache','switch_ols_private_cache','set_ols_private_cache',
            'set_coll_open','get_qrcode_data','check_two_step','set_two_step_auth','create_user','remove_user','modify_user',
            'get_key','get_php_session_path','set_php_session_path','get_cert_source','get_users',
            'set_local','set_debug','get_panel_error_logs','clean_panel_error_logs',
            'get_basic_auth_stat','set_basic_auth','get_cli_php_version','get_tmp_token',
            'set_cli_php_version','DelOldSession', 'GetSessionCount', 'SetSessionConf',
            'GetSessionConf','get_ipv6_listen','set_ipv6_status','GetApacheValue','SetApacheValue',
            'GetNginxValue','SetNginxValue','get_token','set_token','set_admin_path','is_pro',
            'get_php_config','get_config','SavePanelSSL','GetPanelSSL','GetPHPConf','SetPHPConf',
            'GetPanelList','AddPanelInfo','SetPanelInfo','DelPanelInfo','ClickPanelInfo','SetPanelSSL',
            'SetTemplates','Set502','setPassword','setUsername','setPanel','setPathInfo','setPHPMaxSize',
            'getFpmConfig','setFpmConfig','setPHPMaxTime','syncDate','setPHPDisable','SetControl',
            'ClosePanel','AutoUpdatePanel','SetPanelLock','return_mail_list','del_mail_list','add_mail_address','user_mail_send','get_user_mail','set_dingding','get_dingding','get_settings','user_stmp_mail_send','user_dingding_send'
            )
    return publicObject(config.config(),defs,None,pdata)

@app.route('/ajax',methods=method_all)
def ajax(pdata = None):
    comReturn = comm.local()
    if comReturn: return comReturn
    import ajax
    ajaxObject = ajax.ajax()
    defs = ('get_lines','php_info','change_phpmyadmin_ssl_port','set_phpmyadmin_ssl','get_phpmyadmin_ssl',
            'check_user_auth','to_not_beta','get_beta_logs','apple_beta','GetApacheStatus','GetCloudHtml',
            'get_load_average','GetOpeLogs','GetFpmLogs','GetFpmSlowLogs','SetMemcachedCache','GetMemcachedStatus',
            'GetRedisStatus','GetWarning','SetWarning','CheckLogin','GetSpeed','GetAd','phpSort','ToPunycode',
            'GetBetaStatus','SetBeta','setPHPMyAdmin','delClose','KillProcess','GetPHPInfo','GetQiniuFileList',
            'UninstallLib','InstallLib','SetQiniuAS','GetQiniuAS','GetLibList','GetProcessList','GetNetWorkList',
            'GetNginxStatus','GetPHPStatus','GetTaskCount','GetSoftList','GetNetWorkIo','GetDiskIo','GetCpuIo',
            'CheckInstalled','UpdatePanel','GetInstalled','GetPHPConfig','SetPHPConfig')

    return publicObject(ajaxObject,defs,None,pdata)

@app.route('/system',methods=method_all)
def system(pdata = None):
    comReturn = comm.local()
    if comReturn: return comReturn
    import system
    sysObject = system.system()
    defs = ('get_io_info','UpdatePro','GetAllInfo','GetNetWorkApi','GetLoadAverage','ClearSystem',
            'GetNetWorkOld','GetNetWork','GetDiskInfo','GetCpuInfo','GetBootTime','GetSystemVersion',
            'GetMemInfo','GetSystemTotal','GetConcifInfo','ServiceAdmin','ReWeb','RestartServer','ReMemory','RepPanel')
    return publicObject(sysObject,defs,None,pdata)

@app.route('/deployment',methods=method_all)
def deployment(pdata = None):
    comReturn = comm.local()
    if comReturn: return comReturn
    import plugin_deployment
    sysObject = plugin_deployment.plugin_deployment()
    defs = ('GetList','AddPackage','DelPackage','SetupPackage','GetSpeed','GetPackageOther')
    return publicObject(sysObject,defs,None,pdata)

@app.route('/data',methods=method_all)
@app.route('/panel_data',methods=method_all)
def panel_data(pdata = None):
    comReturn = comm.local()
    if comReturn: return comReturn
    import data
    dataObject = data.data()
    defs = ('setPs','getData','getFind','getKey')
    return publicObject(dataObject,defs,None,pdata)

    
@app.route('/code')
def code():
    try:
        import vilidate,time
    except:
        public.ExecShell("pip install Pillow==5.4.1 -I")
        return "Pillow not install!"
    code_time = cache.get('codeOut')
    if code_time: return u'Error: Don\'t request validation codes frequently'
    vie = vilidate.vieCode()
    codeImage = vie.GetCodeImage(80,4)
    if sys.version_info[0] == 2:
        try:
            from cStringIO import StringIO
        except:
            from StringIO import StringIO
        out = StringIO()
    else:
        from io import BytesIO
        out = BytesIO()
    codeImage[0].save(out, "png")
    cache.set("codeStr",public.md5("".join(codeImage[1]).lower()),180)
    cache.set("codeOut",1,0.1)
    out.seek(0)
    return send_file(out, mimetype='image/png', cache_timeout=0)


@app.route('/ssl',methods=method_all)
def ssl(pdata = None):
    comReturn = comm.local()
    if comReturn: return comReturn
    import panelSSL
    toObject = panelSSL.panelSSL()
    defs = ('RemoveCert','renew_lets_ssl','SetCertToSite','GetCertList','SaveCert','GetCert','GetCertName',
            'DelToken','GetToken','GetUserInfo','GetOrderList','GetDVSSL','Completed','SyncOrder',
            'GetSSLInfo','downloadCRT','GetSSLProduct','Renew_SSL','Get_Renew_SSL')
    result = publicObject(toObject,defs,None,pdata)
    return result

@app.route('/task',methods=method_all)
def task(pdata = None):
    comReturn = comm.local()
    if comReturn: return comReturn
    import panelTask
    toObject = panelTask.bt_task()
    defs = ('get_task_lists','remove_task','get_task_find')
    result = publicObject(toObject,defs,None,pdata)
    return result

@app.route('/plugin',methods=method_all)
def plugin(pdata = None):
    comReturn = comm.local()
    if comReturn: return comReturn
    import panelPlugin
    pluginObject = panelPlugin.panelPlugin()
    defs = ('check_install_limit','set_score','get_score','update_zip','input_zip','export_zip','add_index','remove_index','sort_index',
            'install_plugin','uninstall_plugin','get_soft_find','get_index_list','get_soft_list','get_cloud_list',
            'check_deps','flush_cache','GetCloudWarning','install','unInstall','getPluginList','getPluginInfo','get_make_args','add_make_args',
            'getPluginStatus','setPluginStatus','a','getCloudPlugin','getConfigHtml','savePluginSort','del_make_args','set_make_args')
    return publicObject(pluginObject,defs,None,pdata)

@app.route('/public',methods=method_all)
def panel_public():
    get = get_input()
    try:
        import panelWaf
        panelWaf_data = panelWaf.panelWaf()
        if panelWaf_data.is_sql(get.__dict__):return 'ERROR'
        if panelWaf_data.is_xss(get.__dict__):return 'ERROR'
    except:
        pass
    get.client_ip = public.GetClientIp()
    if not hasattr(get,'name'): get.name = ''
    if not hasattr(get,'fun'): return abort(404)
    if not public.path_safe_check("%s/%s" % (get.name,get.fun)): return abort(404)
    if get.fun in ['scan_login', 'login_qrcode', 'set_login', 'is_scan_ok', 'blind','static']:
        if get.fun == 'static':
            if not 'filename' in get: return abort(404)
            if not public.path_safe_check("%s" % (get.filename)): return abort(404)
            s_file = '/www/server/panel/BTPanel/static/' + get.filename
            if s_file.find('..') != -1 or s_file.find('./') != -1: return abort(404)
            if not os.path.exists(s_file): return abort(404)
            return send_file(s_file, conditional=True, add_etags=True)

        #检查是否验证过安全入口
        if get.fun in ['login_qrcode','is_scan_ok']:
            global admin_check_auth,admin_path,route_path,admin_path_file
            if admin_path != '/bt' and os.path.exists(admin_path_file) and  not 'admin_auth' in session:
                return 'False'
        import wxapp
        pluwx = wxapp.wxapp()
        checks = pluwx._check(get)
        if type(checks) != bool or not checks: return public.getJson(checks),json_header
        data = public.getJson(eval('pluwx.'+get.fun+'(get)'))
        return data,json_header
    
    if get.name != 'app': return abort(404)
    import panelPlugin
    plu = panelPlugin.panelPlugin()
    get.s = '_check'
    checks = plu.a(get)
    if type(checks) != bool or not checks: return public.getJson(checks),json_header
    get.s = get.fun
    comm.setSession()
    comm.init()
    comm.checkWebType()
    comm.GetOS()
    result = plu.a(get)
    #session.clear()
    return public.getJson(result),json_header

@app.route('/favicon.ico',methods=method_get)
def send_favicon():
    s_file = '/www/server/panel/BTPanel/static/favicon.ico'
    if not os.path.exists(s_file): return abort(404)
    return send_file(s_file,conditional=True,add_etags=True)


@app.route('/coll',methods=method_all)
@app.route('/coll/',methods=method_all)
@app.route('/<name>/<fun>',methods=method_all)
@app.route('/<name>/<fun>/<path:stype>',methods=method_all)
def panel_other(name=None,fun = None,stype=None):
    if name != "mail_sys" or fun != "send_mail_http.json":
        comReturn = comm.local()
        if comReturn: return comReturn

    is_accept = False
    if not fun: fun = 'index.html'
    if not stype:
        tmp = fun.split('.')
        fun = tmp[0]
        if len(tmp) == 1:  tmp.append('')
        stype = tmp[1]


    if not name: name = 'coll'
    if not public.path_safe_check("%s/%s/%s" % (name,fun,stype)): return abort(404)
    if name.find('./') != -1 or not re.match("^[\w-]+$",name): return abort(404)
    if not name: return public.returnJson(False,public.GetMsg("PLUGIN_INPUT_A")),json_header
    p_path = '/www/server/panel/plugin/' + name
    if not os.path.exists(p_path): return abort(404)

    #是否响插件应静态文件
    if fun == 'static':
        if stype.find('./') != -1 or not os.path.exists(p_path + '/static'): return abort(404)
        s_file = p_path + '/static/' + stype
        if s_file.find('..') != -1: return abort(404)
        if not re.match("^[\w\./-]+$",s_file): return abort(404)
        if not public.path_safe_check(s_file): return abort(404)
        if not os.path.exists(s_file): return abort(404)
        return send_file(s_file,conditional=True,add_etags=True)

    #准备参数
    args = get_input()
    args.client_ip = public.GetClientIp()
    args.fun = fun
    
    #初始化插件对象
    try:
        is_php = os.path.exists(p_path + '/index.php')
        if not is_php:
            sys.path.append(p_path)
            plugin_main = __import__(name+'_main')
            try:
                if sys.version_info[0] == 2:
                    reload(plugin_main)
                else:
                    from imp import reload
                    reload(plugin_main)
            except:pass
            plu = eval('plugin_main.' + name + '_main()')
            if not hasattr(plu,fun):
                return public.returnJson(False,'PLUGIN_NOT_FUN'),json_header

        #执行插件方法
        if not is_php:
            if is_accept:
                checks = plu._check(args)
                if type(checks) != bool or not checks:
                    return public.getJson(checks),json_header
            data = eval('plu.'+fun+'(args)')
        else:
            import panelPHP
            args.s = fun
            args.name = name
            data = panelPHP.panelPHP(name).exec_php_script(args)

        r_type = type(data)
        if r_type == Response: return data

        #处理响应
        if stype == 'json':  #响应JSON
            return public.getJson(data),json_header
        elif stype == 'html':   #使用模板
            t_path_root = p_path + '/templates/'
            t_path = t_path_root + fun + '.html'
            if not os.path.exists(t_path):
                return public.returnJson(False,'PLUGIN_NOT_TEMPLATE'),json_header
            t_body = public.readFile(t_path)

            #处理模板包含
            rep = '{%\s?include\s"(.+)"\s?%}'
            includes = re.findall(rep,t_body)
            for i_file in includes:
                filename = p_path + '/templates/' + i_file
                i_body = 'ERROR: File '+filename+' does not exists.'
                if os.path.exists(filename):
                    i_body = public.readFile(filename)
                t_body = re.sub(rep.replace('(.+)',i_file),i_body,t_body)

            return render_template_string(t_body,data = data)
        else:  #直接响应插件返回值,可以是任意flask支持的响应类型
            r_type = type(data)
            if r_type == dict:
                return public.returnJson(False,public.getMsg('PUBLIC_ERR_RETURN').format(r_type)),json_header
            return data
    except:
        error_info = public.get_error_info()
        public.submit_error(error_info)
        return error_info.replace('\n','<br>\n')


@app.route('/wxapp',methods=method_all)
@app.route('/panel_wxapp',methods=method_all)
def panel_wxapp(pdata = None):
    comReturn = comm.local()
    if comReturn: return comReturn
    import wxapp
    toObject = wxapp.wxapp()
    defs = ('blind','get_safe_log','blind_result','get_user_info','blind_del','blind_qrcode')
    result = publicObject(toObject,defs,None,pdata)
    return result

@app.route('/hook',methods=method_all)
def panel_hook():
    get = get_input()
    if not os.path.exists('plugin/webhook'):
        return public.getJson(public.returnMsg(False,'INIT_WEBHOOK_ERR'))
    sys.path.append('plugin/webhook')
    import webhook_main
    session.clear()
    return public.getJson(webhook_main.webhook_main().RunHook(get))

@app.route('/install',methods=method_all)
def install():
    if public.M('config').where("id=?",('1',)).getField('status') == 1: 
        if os.path.exists('install.pl'): os.remove('install.pl')
        session.clear()
        return redirect('/login')
    ret_login = os.path.join('/',admin_path)
    if admin_path == '/' or admin_path == '/bt': ret_login = '/login'
    session['admin_path'] = False
    session['login'] = False
    if request.method == method_get[0]:
        if not os.path.exists('install.pl'): return redirect(ret_login)
        data = {}
        data['status'] = os.path.exists('install.pl')
        data['username'] = public.GetRandomString(8).lower()
        return render_template( 'install.html',data = data)
    
    elif request.method == method_post[0]:
        if not os.path.exists('install.pl'): return redirect(ret_login)
        get = get_input()
        if not hasattr(get,'bt_username'): return public.GetMsg("LOGIN_USER_EMPTY")
        if not get.bt_username: return public.GetMsg("LOGIN_USER_EMPTY")
        if not hasattr(get,'bt_password1'): return public.GetMsg("LOGIN_USER_EMPTY")
        if not get.bt_password1: return public.GetMsg("LOGIN_USER_EMPTY")
        if get.bt_password1 != get.bt_password2: return public.GetMsg("USER_PASSWORD_CHECK")
        public.M('users').where("id=?",(1,)).save('username,password',(get.bt_username,public.md5(get.bt_password1.strip())))
        os.remove('install.pl')
        public.M('config').where("id=?",('1',)).setField('status',1)
        data = {}
        data['status'] = os.path.exists('install.pl')
        data['username'] = get.bt_username
        return render_template( 'install.html',data = data)


#检查Token
def check_token(data):
    pluginPath = 'plugin/safelogin/token.pl'
    if not os.path.exists(pluginPath): return False
    from urllib import unquote
    from binascii import unhexlify
    from json import loads
        
    result = unquote(unhexlify(data))
    token = public.readFile(pluginPath).strip()
        
    result = loads(result)
    if not result: return False
    if result['token'] != token: return False
    return result


@app.route('/auth',methods=method_all)
def auth(pdata = None):
    comReturn = comm.local()
    if comReturn: return comReturn
    import panelAuth
    toObject = panelAuth.panelAuth()
    defs = ('get_re_order_status_plugin','create_plugin_other_order','get_order_stat',
            'get_voucher_plugin','create_order_voucher_plugin','get_product_discount_by',
            'get_re_order_status','create_order_voucher','create_order','get_order_status',
            'get_voucher','flush_pay_status','create_serverid','check_serverid',
            'get_plugin_list','check_plugin','get_buy_code','check_pay_status',
            'get_renew_code','check_renew_code','get_business_plugin',
            'get_ad_list','check_plugin_end','get_plugin_price')
    result = publicObject(toObject,defs,None,pdata)
    return result


@app.route('/robots.txt',methods=method_all)
def panel_robots():
    robots = '''User-agent: *
Disallow: /
'''
    return robots,{'Content-Type':'text/plain'}

@app.route('/download',methods=method_get)
def download():
    comReturn = comm.local()
    if comReturn: return comReturn
    filename = request.args.get('filename')
    if not filename: return public.ReturnJson(False,"INIT_ARGS_ERR"),json_header
    if filename in ['alioss','qiniu','upyun','txcos','ftp']: return panel_cloud()
    if filename in ['gdrive','gcloud_storage']: return "Google storage products do not currently support downloads"
    if not os.path.exists(filename): return public.ReturnJson(False,"FILE_NOT_EXISTS"),json_header

    if request.args.get('play') == 'true':
        import panelVideo
        start, end = panelVideo.get_range(request)
        return panelVideo.partial_response(filename, start, end)
    else:
        mimetype = "application/octet-stream"
        extName = filename.split('.')[-1]
        if extName in ['png','gif','jpeg','jpg']: mimetype = None
        return send_file(filename,mimetype=mimetype,
                         as_attachment=True,
                         attachment_filename=os.path.basename(filename),
                         cache_timeout=0)

def get_dir_down(filename,token,find):
    import files
    args = public.dict_obj()
    args.path = filename
    to_path = filename.replace(find['filename'],'').strip('/')

    if request.args.get('play') == 'true':
        pdata = files.files().get_videos(args)
        return public.GetJson(pdata),json_header
    else:
        pdata = files.files().GetDir(args)
        pdata['token'] = token
        pdata['src_path'] = find['filename']
        pdata['to_path'] = to_path
        pdata['expire'] = public.format_date(times=find['expire'])
        pdata['filename'] = (find['filename'].split('/')[-1] + '/' + to_path).strip('/')
        return render_template('down.html',data = pdata,to_size=public.to_size)

@app.route('/down/<token>',methods=method_all)
def down(token=None,fname=None):
    try:
        fname = request.args.get('fname')
        if fname:
            if(len(fname) > 256): return abort(404)
        if fname: fname = fname.strip('/')
        if not token: return abort(404)
        if len(token) != 12: return abort(404)
        if not request.args.get('play') in ['true',None,'']:
            return abort(404)

        if not re.match(r"^\w+$",token): return abort(404)
        find = public.M('download_token').where('token=?',(token,)).find()

        if not find: return abort(404)
        if time.time() > int(find['expire']): return abort(404)

        if not os.path.exists(find['filename']): return abort(404)
        if find['password'] and not token in session:
            args = get_input()
            if 'file_password' in args:
                if not re.match(r"^\w+$",args.file_password):
                    return public.ReturnJson(False,'Wrong password!'),json_header
                if re.match(r"^\d+$",args.file_password):
                    args.file_password += '.0'
                if args.file_password != str(find['password']):
                    return public.ReturnJson(False,'Wrong password!'),json_header
                session[token] = 1
                session['down'] = True
            else:
                pdata = {
                        "to_path":"",
                        "src_path": find['filename'],
                        "password":True,
                        "filename":find['filename'].split('/')[-1],
                        "total":find['total'],
                        "token":find['token'],
                        "expire":public.format_date(times=find['expire'])
                    }
                session['down'] = True
                return render_template('down.html',data = pdata)

        if not find['password']:
            session['down'] = True
            session[token] = 1

        if session[token] != 1:
            return abort(404)

        filename = find['filename']
        if fname:
            filename = os.path.join(filename,fname)
            if not public.path_safe_check(fname,False): return abort(404)
            if os.path.isdir(filename):
                return get_dir_down(filename,token,find)
        else:
            if os.path.isdir(filename):
                return get_dir_down(filename,token,find)

        if request.args.get('play') == 'true':
            import panelVideo
            start, end = panelVideo.get_range(request)
            return panelVideo.partial_response(filename, start, end)
        else:
            mimetype = "application/octet-stream"
            extName = filename.split('.')[-1]
            if extName in ['png','gif','jpeg','jpg']: mimetype = None
            return send_file(filename,mimetype=mimetype,
                            as_attachment=True,
                            attachment_filename=os.path.basename(filename),
                            cache_timeout=0)
    except:
        return abort(404)


@app.route('/cloud',methods=method_get)
def panel_cloud():
    comReturn = comm.local()
    if comReturn: return comReturn
    get = get_input()
    if not os.path.exists('plugin/' + get.filename + '/' + get.filename+'_main.py'):
        return public.returnJson(False,'INIT_PLUGIN_NOT_EXISTS'),json_header
    sys.path.append('plugin/' + get.filename)
    plugin_main = __import__(get.filename+'_main')
    reload(plugin_main)
    tmp = eval("plugin_main.%s_main()" % get.filename)
    if not hasattr(tmp,'download_file'): return public.returnJson(False,'INIT_PLUGIN_NOT_DOWN_FUN'),json_header
    if get.filename == 'ftp':
        download_url = tmp.getFile(get.name)
    else:
        download_url = tmp.download_file(get.name)
        if download_url.find('http') != 0:download_url = 'http://' + download_url
    return redirect(download_url)

def check_csrf():
    if app.config['DEBUG']: return True
    request_token = request.cookies.get('request_token')
    if session['request_token'] != request_token: return False
    http_token = request.headers.get('x-http-token')
    if not http_token: return False
    if http_token != session['request_token_head']: return False
    cookie_token = request.headers.get('x-cookie-token')
    if cookie_token != session['request_token']: return False
    return True

def publicObject(toObject,defs,action=None,get = None):
    if 'request_token' in session and 'login' in session:
        if not check_csrf(): return public.ReturnJson(False,'Csrf-Token error.'),json_header

    if not get: get = get_input()
    if action: get.action = action

    if hasattr(get,'path'):
            get.path = get.path.replace('//','/').replace('\\','/')
            if get.path.find('./') != -1: return public.ReturnJson(False,'INIT_PATH_NOT_SAFE'),json_header
            if get.path.find('->') != -1:
                get.path = get.path.split('->')[0].strip()
    if hasattr(get,'sfile'):
        get.sfile = get.sfile.replace('//','/').replace('\\','/')
    if hasattr(get,'dfile'):
        get.dfile = get.dfile.replace('//','/').replace('\\','/')

    if hasattr(toObject,'site_path_check'):
        if not toObject.site_path_check(get): return public.ReturnJson(False,'Excessive operation!'),json_header

    p = run_exec()
    result =  p.run(toObject,defs,get)
    del p
    return result


def check_login(http_token=None):
    if cache.get('dologin'): return False
    if 'login' in session: 
        loginStatus = session['login']
        if loginStatus and http_token:
            if session['request_token_head'] != http_token: return False
        return loginStatus
    return False

def get_pd():
    tmp = -1
    try:
        import panelPlugin
        tmp1 = panelPlugin.panelPlugin().get_cloud_list()
    except:
        tmp1 = None
    if tmp1:
        tmp = tmp1[public.to_string([112,114,111])]
        ltd = tmp1.get('ltd',-1)
    else:
        ltd = -1
        tmp4 = cache.get(public.to_string([112, 95, 116, 111, 107, 101, 110]))
        if tmp4:
            tmp_f = public.to_string([47, 116, 109, 112, 47]) + tmp4
            if not os.path.exists(tmp_f): public.writeFile(tmp_f,'-1')
            tmp = public.readFile(tmp_f)
            if tmp: tmp = int(tmp)

    if ltd < 1:
        if ltd == -2:
            tmp3 = public.to_string([60, 115, 112, 97, 110, 32, 99, 108, 97, 115, 115, 61, 34, 98, 116, 108, 116, 100,
            45, 103, 114, 97, 121, 34, 62, 60, 115, 112, 97, 110, 32, 115, 116, 121, 108, 101,
            61, 34, 99, 111, 108, 111, 114, 58, 32, 35, 102, 99, 54, 100, 50, 54, 59, 102, 111,
            110, 116, 45, 119, 101, 105, 103, 104, 116, 58, 32, 98, 111, 108, 100, 59, 109, 97,
            114, 103, 105, 110, 45, 114, 105, 103, 104, 116, 58, 53, 112, 120, 34, 62, 24050, 36807,
            26399, 60, 47, 115, 112, 97, 110, 62, 60, 97, 32, 99, 108, 97, 115, 115, 61, 34, 98, 116,
            108, 105, 110, 107, 34, 32, 111, 110, 99, 108, 105, 99, 107, 61, 34, 98, 116, 46, 115, 111,
            102, 116, 46, 117, 112, 100, 97, 116, 97, 95, 108, 116, 100, 40, 41, 34, 62, 32493,
            36153, 60, 47, 97, 62, 60, 47, 115, 112, 97, 110, 62])
        elif tmp == -1:
            tmp3 = public.to_string([60, 115, 112, 97, 110, 32, 99, 108, 97, 115, 115, 61, 34, 98,
                                    116, 112, 114, 111, 45, 102, 114, 101, 101, 34, 32, 111, 110, 99, 108, 105, 99, 107,
                                    61, 34, 98, 116, 46, 115, 111, 102, 116, 46, 117, 112, 100, 97, 116, 97, 95, 99,
                                    111, 109, 109, 101, 114, 99, 105, 97, 108, 95, 118, 105, 101, 119, 40, 41, 34,
                                    32, 116, 105, 116, 108, 101, 61, 34, 28857, 20987, 21319, 32423, 21040,
                                        21830, 19994, 29256, 34, 62, 20813, 36153, 29256, 60, 47, 115, 112, 97, 110, 62])
        elif tmp == -2:
            tmp3 = public.to_string([60, 115, 112, 97, 110, 32, 99, 108, 97, 115, 115, 61, 34, 98, 116,
                                    112, 114, 111, 45, 103, 114, 97, 121, 34, 62, 60, 115, 112, 97, 110, 32,
                                    115, 116, 121, 108, 101, 61, 34, 99, 111, 108, 111, 114, 58, 32, 35,
                                    102, 99, 54, 100, 50, 54, 59, 102, 111, 110, 116, 45, 119, 101, 105, 103,
                                    104, 116, 58, 32, 98, 111, 108, 100, 59, 109, 97, 114, 103, 105, 110, 45,
                                    114, 105, 103, 104, 116, 58, 53, 112, 120, 34, 62, 24050, 36807, 26399,
                                    60, 47, 115, 112, 97, 110, 62, 60, 97, 32, 99, 108, 97, 115, 115, 61, 34,
                                    98, 116, 108, 105, 110, 107, 34, 32, 111, 110, 99, 108, 105, 99, 107, 61,
                                    34, 98, 116, 46, 115, 111, 102, 116, 46, 117, 112, 100, 97, 116, 97, 95,
                                    112, 114, 111, 40, 41, 34, 62, 32493, 36153, 60, 47, 97, 62, 60,
                                    47, 115, 112, 97, 110, 62])
        elif tmp >= 0:
            if tmp == 0:
                tmp2 = public.to_string([27704,20037,25480,26435])
                tmp3 = public.to_string([60, 115, 112, 97, 110, 32, 99, 108, 97, 115, 115, 61, 34, 98, 116,
                                        112, 114, 111, 34, 62, 123, 48, 125, 60, 115, 112, 97, 110, 32, 115, 116,
                                        121, 108, 101, 61, 34, 99, 111, 108, 111, 114, 58, 32, 35, 102, 99, 54, 100,
                                        50, 54, 59, 102, 111, 110, 116, 45, 119, 101, 105, 103, 104, 116,
                                        58, 32, 98, 111, 108, 100, 59, 34, 62, 123, 49, 125, 60, 47, 115,
                                        112, 97, 110, 62, 60, 47, 115, 112, 97, 110, 62]).format(
                                            public.to_string([21040,26399,26102,38388,65306]),tmp2)
            else:
                tmp2 = time.strftime(public.to_string([37, 89, 45, 37, 109, 45, 37, 100]),time.localtime(tmp))
                tmp3 = public.to_string([60, 115, 112, 97, 110, 32, 99, 108, 97, 115, 115, 61, 34, 98, 116,
                                        112, 114, 111, 34, 62, 21040, 26399, 26102, 38388, 65306, 60, 115, 112,
                                        97, 110, 32, 115, 116, 121, 108, 101, 61, 34, 99, 111, 108, 111, 114,
                                        58, 32, 35, 102, 99, 54, 100, 50, 54, 59, 102, 111, 110, 116, 45, 119,
                                        101, 105, 103, 104, 116, 58, 32, 98, 111, 108, 100, 59, 109, 97, 114,
                                        103, 105, 110, 45, 114, 105, 103, 104, 116, 58, 53, 112, 120, 34, 62, 123,
                                        48, 125, 60, 47, 115, 112, 97, 110, 62, 60, 97, 32, 99, 108, 97, 115,
                                        115, 61, 34, 98, 116, 108, 105, 110, 107, 34, 32, 111, 110, 99, 108, 105, 99,
                                        107, 61, 34, 98, 116, 46, 115, 111, 102, 116, 46, 117, 112, 100, 97,
                                        116, 97, 95, 112, 114, 111, 40, 41, 34, 62, 32493, 36153, 60, 47, 97, 62, 60,
                                        47, 115, 112, 97, 110, 62]).format(tmp2)
        else:
            tmp3 = public.to_string([60, 115, 112, 97, 110, 32, 99, 108, 97, 115, 115, 61, 34, 98, 116, 112,
                                    114, 111, 45, 103, 114, 97, 121, 34, 32, 111, 110, 99, 108, 105, 99, 107,
                                    61, 34, 98, 116, 46, 115, 111, 102, 116, 46, 117, 112, 100, 97, 116, 97,
                                    95, 112, 114, 111, 40, 41, 34, 32, 116, 105, 116, 108, 101, 61, 34, 28857,
                                    20987, 21319, 32423, 21040, 19987, 19994, 29256, 34, 62, 20813, 36153,
                                    29256, 60, 47, 115, 112, 97, 110, 62])
    else:
        tmp3 = public.to_string([60, 115, 112, 97, 110, 32, 99, 108, 97, 115, 115, 61, 34, 98, 116, 108, 116,
                                    100, 34, 62, 21040, 26399, 26102, 38388, 65306, 60, 115, 112, 97, 110, 32, 115, 116,
                                    121, 108, 101, 61, 34, 99, 111, 108, 111, 114, 58, 32, 35, 102, 99, 54, 100, 50,
                                    54, 59, 102, 111, 110, 116, 45, 119, 101, 105, 103, 104, 116, 58, 32, 98, 111,
                                    108, 100, 59, 109, 97, 114, 103, 105, 110, 45, 114, 105, 103, 104, 116, 58, 53,
                                    112, 120, 34, 62, 123, 125, 60, 47, 115, 112, 97, 110, 62, 60, 97, 32, 99, 108,
                                    97, 115, 115, 61, 34, 98, 116, 108, 105, 110, 107, 34, 32, 111, 110, 99, 108, 105,
                                    99, 107, 61, 34, 98, 116, 46, 115, 111, 102, 116, 46, 117, 112, 100, 97, 116, 97,
                                    95, 108, 116, 100, 40, 41, 34, 62, 32493, 36153, 60, 47, 97, 62, 60, 47, 115,
                                    112, 97, 110, 62]).format(time.strftime(public.to_string([37, 89, 45, 37, 109, 45, 37, 100]),time.localtime(ltd)))

    return tmp3,tmp,ltd


@app.errorhandler(404)
def notfound(e):
    errorStr = public.ReadFile('./BTPanel/templates/' + public.GetConfigValue('template') + '/error.html')
    try:
        errorStr = errorStr.format(public.getMsg('PAGE_ERR_404_TITLE'),
                                   public.getMsg('PAGE_ERR_404_H1'),
                                   public.getMsg('PAGE_ERR_404_P1'),
                                   public.getMsg('NAME'),
                                   public.getMsg('PAGE_ERR_HELP'))
    except IndexError: pass
    return errorStr,404
  
@app.errorhandler(500)
def internalerror(e):
    #if str(e).find('Permanent Redirect') != -1: return e
    errorStr = public.ReadFile('./BTPanel/templates/' + public.GetConfigValue('template') + '/error.html')
    try:
        if not app.config['DEBUG']:
            errorStr = errorStr.format(public.getMsg('PAGE_ERR_500_TITLE'),
                                       public.getMsg('PAGE_ERR_500_H1'),
                                       public.getMsg('PAGE_ERR_500_P1'),
                                       public.getMsg('NAME'),
                                       public.getMsg('PAGE_ERR_HELP'))
        else:
            errorStr = errorStr.format(public.getMsg('PAGE_ERR_500_TITLE'),str(e),'<pre>'+public.get_error_info() + '</pre>','The above debugging information is only displayed in developer mode','Version: ' + public.version())
    except IndexError:pass
    return errorStr,500


#获取输入数据
def get_input():
    data = common.dict_obj()
    exludes = ['blob']
    for key in request.args.keys():
        data[key] = str(request.args.get(key,''))
    try:
        for key in request.form.keys():
            if key in exludes: continue
            data[key] = str(request.form.get(key,''))
    except:
        try:
            post = request.form.to_dict()
            for key in post.keys():
                if key in exludes: continue
                data[key] = str(post[key])
        except:
            pass

    if 'form_data' in g:
        for k in g.form_data.keys():
            data[k] = str(g.form_data[k])

    if not hasattr(data,'data'): data.data = []
    return data

#取数据对象
def get_input_data(data):
    pdata = common.dict_obj()
    for key in data.keys():
        pdata[key] = str(data[key])
    return pdata


class run_exec:
    def run(self,toObject,defs,get):
        result = None
        for key in defs:
            if key == get.action:
                fun = 'toObject.'+key+'(get)'
                if hasattr(get,'html') or hasattr(get,'s_module'):
                    result =  eval(fun)
                else:
                    result =  public.GetJson(eval(fun)),json_header
        if not result:
            result = public.ReturnJson(False,'ARGS_ERR'),json_header
        if g.is_aes:
            result = public.aes_encrypt(result[0],g.aes_key),json_header
        return result