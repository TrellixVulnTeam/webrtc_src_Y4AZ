// Copyright 2015 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

Polymer({
  is: 'local-state',
  properties: {
    /**
     * The current CryptAuth enrollment status.
     * @type {{
     *   lastSuccessTime: ?number,
     *   nextRefreshTime: ?number,
     *   recoveringFromFailure: boolean,
     *   operationInProgress: boolean,
     * }} SyncState
     */
    enrollmentState_: {
      type: Object,
      value: {
        lastSuccessTime: null,
        nextRefreshTime: null,
        recoveringFromFailure: true,
        operationInProgress: false,
      },
    },

    /**
     * The current CryptAuth device sync status.
     * @type {SyncState}
     */
    deviceSyncState_: {
      type: Object,
      value: {
        lastSuccessTime: null,
        nextRefreshTime: null,
        recoveringFromFailure: true,
        operationInProgress: false,
      },
    },

    /**
     * List of unlock keys that can unlock the local device.
     * @type {Array<DeviceInfo>}
     */
    unlockKeys_: {
      type: Array,
      value: [
        {
         publicKey: 'CAESRQogOlH8DgPMQu7eAt-b6yoTXcazG8mAl6SPC5Ds-LTULIcSIQDZ' +
                    'DMqsoYRO4tNMej1FBEl1sTiTiVDqrcGq-CkYCzDThw==',
         friendlyDeviceName: 'LGE Nexus 4',
         bluetoothAddress: 'C4:43:8F:12:07:07',
         unlockKey: true,
         unlockable: false,
         connectionStatus: 'connected',
         remoteState: {
           userPresent: true,
           secureScreenLock: true,
           trustAgent: true
         },
        },
      ],
    },
  },

  /**
   * Called when the page is about to be shown.
   */
  activate: function() {
    SyncStateInterface = this;
    chrome.send('getEnrollmentState');
  },

  /**
   * Immediately forces an enrollment attempt.
   */
  forceEnrollment_: function() {
    chrome.send('forceEnrollment');
  },

  /**
   * Called when the enrollment state changes.
   * @param {SyncState} enrollmentState
   */
  onEnrollmentStateChanged: function(enrollmentState) {
    this.enrollmentState_ = enrollmentState;
  },

  /**
   * Called when the device sync state changes.
   * @param {SyncState} deviceSyncState
   */
  onDeviceSyncStateChanged: function(deviceSyncState) {},

  /**
   * Called for the chrome.send('getEnrollmentState') response.
   * @param {SyncState} enrollmentState
   */
  onGotEnrollmentState: function(enrollmentState) {
    this.enrollmentState_ = enrollmentState;
  },

  /**
   * Called for the chrome.send('getDeviceSyncState') response.
   * @param {SyncState} enrollmentState
   */
  onGotDeviceSyncState: function(deviceSyncState) {},

  /**
   * @param {SyncState} syncState The enrollment or device sync state.
   * @param {string} neverSyncedString String returned if there has never been a
   *     last successful sync.
   * @return {string} The formatted string of the last successful sync time.
   */
  getLastSyncTimeString_: function(syncState, neverSyncedString) {
    if (syncState.lastSuccessTime == 0)
      return neverSyncedString;
    var date = new Date(syncState.lastSuccessTime);
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
  },

  /**
   * @param {SyncState} syncState The enrollment or device sync state.
   * @return {string} The formatted string to be displayed.
   */
  getNextEnrollmentString_: function(syncState) {
    var deltaMillis = syncState.nextRefreshTime;
    if (deltaMillis == null)
      return 'unknown';
    if (deltaMillis == 0)
      return 'sync in progress...';

    var seconds = deltaMillis / 1000;
    if (seconds < 60)
      return Math.round(seconds) + ' seconds to refresh';

    var minutes = seconds / 60;
    if (minutes < 60)
      return Math.round(minutes) + ' minutes to refresh';

    var hours = minutes / 60;
    if (hours < 24)
      return Math.round(hours) + ' hours to refresh';

    var days = hours / 24;
    return Math.round(days) + ' days to refresh';
  },

  /**
   * @param {SyncState} syncState The enrollment or device sync state.
   * @return {string} The icon to show for the current state.
   */
  getNextSyncIcon_: function(syncState) {
    return syncState.operationInProgress ? 'icons:refresh' : 'icons:schedule';
 },

  /**
   * @param {SyncState} syncState The enrollment or device sync state.
   * @return {string} The icon id representing whether the last sync is
   *     successful.
   */
  getIconForSuccess_: function(syncState) {
    return syncState.recoveringFromFailure ?
        'icons:error' : 'icons:cloud-done';
  },
});

// Interface with the native WebUI component for the CryptAuthSync state (i.e.
// enrollment and device sync).
SyncStateInterface = {
  /**
   * Called when the enrollment state changes. For example, when a new
   * enrollment is initiated.
   * @type {function(SyncState)}
   */
  onEnrollmentStateChanged: function(enrollmentState) {},

  /**
   * Called when the device state changes. For example, when a new device sync
   * is initiated.
   * @type {function(DeviceSyncState)}
   */
  onDeviceSyncStateChanged: function(deviceSyncState) {},

  /**
   * Called in response to chrome.send('getEnrollmentState') with the current
   * enrollment status of the user and device.
   * @type {function(SyncState)}
   */
  onGotEnrollmentState: function(enrollmentState) {},

  /**
   * Called in response to chrome.send('getDeviceState') with the current
   * enrollment status of the user and device.
   * @type {function(DeviceSyncState)}
   */
  onGotDeviceSyncState: function(deviceSyncState) {},
};
