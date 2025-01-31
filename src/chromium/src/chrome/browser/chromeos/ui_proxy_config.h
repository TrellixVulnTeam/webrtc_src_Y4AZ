// Copyright 2013 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef CHROME_BROWSER_CHROMEOS_UI_PROXY_CONFIG_H_
#define CHROME_BROWSER_CHROMEOS_UI_PROXY_CONFIG_H_

#include <string>

#include "components/proxy_config/proxy_prefs.h"
#include "net/proxy/proxy_bypass_rules.h"
#include "net/proxy/proxy_server.h"
#include "url/gurl.h"

namespace base {
class DictionaryValue;
}

namespace net {
class ProxyConfig;
}

namespace chromeos {

// Contrary to other platforms which simply use the systems' UI to allow users
// to configure proxies, we have to implement our own UI on the chromeos device.
// This requires extra and specific UI requirements that net::ProxyConfig does
// not supply.  So we create an augmented analog to net::ProxyConfig here to
// include and handle these UI requirements, e.g.
// - state of configuration e.g. where it was picked up from - policy,
//   extension, etc (refer to ProxyPrefs::ConfigState)
// - the read/write access of a proxy setting
// - may add more stuff later.
// This is then converted to the common net::ProxyConfig before being pushed
// to PrefProxyConfigTrackerImpl::OnProxyConfigChanged and then to the network
// stack.
struct UIProxyConfig {
  // Specifies if proxy config is direct, auto-detect, using pac script,
  // single-proxy, or proxy-per-scheme.
  enum Mode {
    MODE_DIRECT,
    MODE_AUTO_DETECT,
    MODE_PAC_SCRIPT,
    MODE_SINGLE_PROXY,
    MODE_PROXY_PER_SCHEME,
  };

  // Proxy setting for mode = direct or auto-detect or using pac script.
  struct AutomaticProxy {
    GURL pac_url;  // Set if proxy is using pac script.
  };

  // Proxy setting for mode = single-proxy or proxy-per-scheme.
  struct ManualProxy {
    net::ProxyServer server;
  };

  UIProxyConfig();
  ~UIProxyConfig();

  void SetPacUrl(const GURL& pac_url);
  void SetSingleProxy(const net::ProxyServer& server);

  // |scheme| is one of "http", "https", "ftp" or "socks".
  void SetProxyForScheme(const std::string& scheme,
                         const net::ProxyServer& server);

  // Only valid for MODE_SINGLE_PROXY or MODE_PROXY_PER_SCHEME.
  void SetBypassRules(const net::ProxyBypassRules& rules);

  // Converts net::ProxyConfig to |this|.
  bool FromNetProxyConfig(const net::ProxyConfig& net_config);

  // Converts |this| to Dictionary of ProxyConfigDictionary format (which
  // is the same format used by prefs).
  base::DictionaryValue* ToPrefProxyConfig() const;

  // Map |scheme| (one of "http", "https", "ftp" or "socks") to the correct
  // ManualProxy.  Returns NULL if scheme is invalid.
  ManualProxy* MapSchemeToProxy(const std::string& scheme);

  // Encodes the proxy server as "<url-scheme>=<proxy-scheme>://<proxy>"
  static void EncodeAndAppendProxyServer(const std::string& url_scheme,
                                         const net::ProxyServer& server,
                                         std::string* spec);

  Mode mode;

  ProxyPrefs::ConfigState state;

  // True if user can modify proxy settings via UI.
  // If proxy is managed by policy or extension or other_precde or is for
  // shared network but kUseSharedProxies is turned off, it can't be modified
  // by user.
  bool user_modifiable;

  // Set if mode is MODE_DIRECT or MODE_AUTO_DETECT or MODE_PAC_SCRIPT.
  AutomaticProxy  automatic_proxy;
  // Set if mode is MODE_SINGLE_PROXY.
  ManualProxy     single_proxy;
  // Set if mode is MODE_PROXY_PER_SCHEME and has http proxy.
  ManualProxy     http_proxy;
  // Set if mode is MODE_PROXY_PER_SCHEME and has https proxy.
  ManualProxy     https_proxy;
  // Set if mode is MODE_PROXY_PER_SCHEME and has ftp proxy.
  ManualProxy     ftp_proxy;
  // Set if mode is MODE_PROXY_PER_SCHEME and has socks proxy.
  ManualProxy     socks_proxy;

  // Exceptions for when not to use a proxy.
  net::ProxyBypassRules bypass_rules;
};

}  // namespace chromeos

#endif  // CHROME_BROWSER_CHROMEOS_UI_PROXY_CONFIG_H_
