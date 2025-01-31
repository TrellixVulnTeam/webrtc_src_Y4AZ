// Copyright 2015 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "net/proxy/mojo_proxy_resolver_factory_impl.h"

#include <string>

#include "base/stl_util.h"
#include "net/base/net_errors.h"
#include "net/dns/host_resolver_mojo.h"
#include "net/proxy/mojo_proxy_resolver_impl.h"
#include "net/proxy/proxy_resolver_error_observer_mojo.h"
#include "net/proxy/proxy_resolver_factory.h"
#include "net/proxy/proxy_resolver_v8.h"
#include "net/proxy/proxy_resolver_v8_tracing_wrapper.h"

namespace net {
namespace {

scoped_ptr<ProxyResolverErrorObserver> ReturnErrorObserver(
    scoped_ptr<ProxyResolverErrorObserver> error_observer) {
  return error_observer;
}

scoped_ptr<ProxyResolverFactory> CreateDefaultProxyResolver(
    HostResolver* host_resolver,
    scoped_ptr<ProxyResolverErrorObserver> error_observer) {
  return make_scoped_ptr(new ProxyResolverFactoryV8TracingWrapper(
      host_resolver, nullptr,
      base::Bind(&ReturnErrorObserver, base::Passed(&error_observer))));
}

// A class to manage the lifetime of a MojoProxyResolverImpl and a
// HostResolverMojo. An instance will remain while the message pipes for both
// mojo connections remain open.
class MojoProxyResolverHolder {
 public:
  MojoProxyResolverHolder(
      scoped_ptr<HostResolverMojo> host_resolver,
      scoped_ptr<ProxyResolver> proxy_resolver_impl,
      mojo::InterfaceRequest<interfaces::ProxyResolver> request);

 private:
  // Mojo error handler.
  void OnConnectionError();

  scoped_ptr<HostResolverMojo> host_resolver_;
  MojoProxyResolverImpl mojo_proxy_resolver_;
  mojo::Binding<interfaces::ProxyResolver> binding_;

  DISALLOW_COPY_AND_ASSIGN(MojoProxyResolverHolder);
};

MojoProxyResolverHolder::MojoProxyResolverHolder(
    scoped_ptr<HostResolverMojo> host_resolver,
    scoped_ptr<ProxyResolver> proxy_resolver_impl,
    mojo::InterfaceRequest<interfaces::ProxyResolver> request)
    : host_resolver_(host_resolver.Pass()),
      mojo_proxy_resolver_(proxy_resolver_impl.Pass()),
      binding_(&mojo_proxy_resolver_, request.Pass()) {
  binding_.set_connection_error_handler(base::Bind(
      &MojoProxyResolverHolder::OnConnectionError, base::Unretained(this)));
  host_resolver_->set_disconnect_callback(base::Bind(
      &MojoProxyResolverHolder::OnConnectionError, base::Unretained(this)));
}

void MojoProxyResolverHolder::OnConnectionError() {
  delete this;
}

}  // namespace

class MojoProxyResolverFactoryImpl::Job {
 public:
  Job(MojoProxyResolverFactoryImpl* parent,
      const scoped_refptr<ProxyResolverScriptData>& pac_script,
      const MojoProxyResolverFactoryImpl::Factory& proxy_resolver_factory,
      mojo::InterfaceRequest<interfaces::ProxyResolver> request,
      interfaces::HostResolverPtr host_resolver,
      interfaces::ProxyResolverErrorObserverPtr error_observer,
      interfaces::ProxyResolverFactoryRequestClientPtr client);
  ~Job();

 private:
  // Mojo error handler.
  void OnConnectionError();

  void OnProxyResolverCreated(int error);

  MojoProxyResolverFactoryImpl* const parent_;
  scoped_ptr<HostResolverMojo> host_resolver_;
  scoped_ptr<ProxyResolver> proxy_resolver_impl_;
  mojo::InterfaceRequest<interfaces::ProxyResolver> proxy_request_;
  scoped_ptr<net::ProxyResolverFactory> factory_;
  scoped_ptr<net::ProxyResolverFactory::Request> request_;
  interfaces::ProxyResolverFactoryRequestClientPtr client_ptr_;

  DISALLOW_COPY_AND_ASSIGN(Job);
};

MojoProxyResolverFactoryImpl::Job::Job(
    MojoProxyResolverFactoryImpl* factory,
    const scoped_refptr<ProxyResolverScriptData>& pac_script,
    const MojoProxyResolverFactoryImpl::Factory& proxy_resolver_factory,
    mojo::InterfaceRequest<interfaces::ProxyResolver> request,
    interfaces::HostResolverPtr host_resolver,
    interfaces::ProxyResolverErrorObserverPtr error_observer,
    interfaces::ProxyResolverFactoryRequestClientPtr client)
    : parent_(factory),
      host_resolver_(new HostResolverMojo(
          host_resolver.Pass(),
          base::Bind(&MojoProxyResolverFactoryImpl::Job::OnConnectionError,
                     base::Unretained(this)))),
      proxy_request_(request.Pass()),
      factory_(proxy_resolver_factory.Run(
          host_resolver_.get(),
          ProxyResolverErrorObserverMojo::Create(error_observer.Pass()))),
      client_ptr_(client.Pass()) {
  client_ptr_.set_connection_error_handler(
      base::Bind(&MojoProxyResolverFactoryImpl::Job::OnConnectionError,
                 base::Unretained(this)));
  factory_->CreateProxyResolver(
      pac_script, &proxy_resolver_impl_,
      base::Bind(&MojoProxyResolverFactoryImpl::Job::OnProxyResolverCreated,
                 base::Unretained(this)),
      &request_);
}

MojoProxyResolverFactoryImpl::Job::~Job() = default;

void MojoProxyResolverFactoryImpl::Job::OnConnectionError() {
  client_ptr_->ReportResult(ERR_PAC_SCRIPT_TERMINATED);
  parent_->RemoveJob(this);
}

void MojoProxyResolverFactoryImpl::Job::OnProxyResolverCreated(int error) {
  if (error == OK) {
    // The MojoProxyResolverHolder will delete itself if either
    // |host_resolver_| or |proxy_request_| encounters a connection error.
    new MojoProxyResolverHolder(host_resolver_.Pass(),
                                proxy_resolver_impl_.Pass(),
                                proxy_request_.Pass());
  }
  client_ptr_->ReportResult(error);
  parent_->RemoveJob(this);
}

MojoProxyResolverFactoryImpl::MojoProxyResolverFactoryImpl(
    const MojoProxyResolverFactoryImpl::Factory& proxy_resolver_factory,
    mojo::InterfaceRequest<interfaces::ProxyResolverFactory> request)
    : proxy_resolver_impl_factory_(proxy_resolver_factory),
      binding_(this, request.Pass()) {
}

MojoProxyResolverFactoryImpl::MojoProxyResolverFactoryImpl(
    mojo::InterfaceRequest<interfaces::ProxyResolverFactory> request)
    : MojoProxyResolverFactoryImpl(base::Bind(&CreateDefaultProxyResolver),
                                   request.Pass()) {
}

MojoProxyResolverFactoryImpl::~MojoProxyResolverFactoryImpl() {
  STLDeleteElements(&jobs_);
}

void MojoProxyResolverFactoryImpl::CreateResolver(
    const mojo::String& pac_script,
    mojo::InterfaceRequest<interfaces::ProxyResolver> request,
    interfaces::HostResolverPtr host_resolver,
    interfaces::ProxyResolverErrorObserverPtr error_observer,
    interfaces::ProxyResolverFactoryRequestClientPtr client) {
  // The Job will call RemoveJob on |this| when either the create request
  // finishes or |request| or |client| encounters a connection error.
  jobs_.insert(new Job(
      this, ProxyResolverScriptData::FromUTF8(pac_script.To<std::string>()),
      proxy_resolver_impl_factory_, request.Pass(), host_resolver.Pass(),
      error_observer.Pass(), client.Pass()));
}

void MojoProxyResolverFactoryImpl::RemoveJob(Job* job) {
  size_t erased = jobs_.erase(job);
  DCHECK_EQ(1u, erased);
  delete job;
}

}  // namespace net
