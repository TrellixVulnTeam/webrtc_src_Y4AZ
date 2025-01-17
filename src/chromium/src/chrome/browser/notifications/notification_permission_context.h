// Copyright 2015 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef CHROME_BROWSER_NOTIFICATIONS_NOTIFICATION_PERMISSION_CONTEXT_H_
#define CHROME_BROWSER_NOTIFICATIONS_NOTIFICATION_PERMISSION_CONTEXT_H_

#include "chrome/browser/content_settings/permission_context_base.h"
#include "components/content_settings/core/common/content_settings.h"

class GURL;
class Profile;

class NotificationPermissionContext : public PermissionContextBase {
 public:
  explicit NotificationPermissionContext(Profile* profile);
  ~NotificationPermissionContext() override;

  // PermissionContextBase implementation.
  void ResetPermission(const GURL& requesting_origin,
                       const GURL& embedder_origin) override;

 private:
  FRIEND_TEST_ALL_PREFIXES(NotificationPermissionContextTest,
                           IgnoresEmbedderOrigin);
  FRIEND_TEST_ALL_PREFIXES(NotificationPermissionContextTest,
                           NoSecureOriginRequirement);

  // PermissionContextBase implementation.
  void UpdateContentSetting(const GURL& requesting_origin,
                            const GURL& embedder_origin,
                            ContentSetting content_setting) override;
  bool IsRestrictedToSecureOrigins() const override;
};

#endif  // CHROME_BROWSER_NOTIFICATIONS_NOTIFICATION_PERMISSION_CONTEXT_H_
