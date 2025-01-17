// Copyright 2015 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

package org.chromium.content.browser;

import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.net.ConnectivityManager;
import android.test.InstrumentationTestCase;
import android.test.suitebuilder.annotation.SmallTest;

import org.chromium.base.test.util.AdvancedMockContext;
import org.chromium.base.test.util.Feature;

/**
 * Tests {@link BackgroundSyncLauncherService} and {@link BackgroundSyncLauncherService.Receiver}.
 */
public class BackgroundSyncLauncherTest extends InstrumentationTestCase {
    private Context mContext;
    private BackgroundSyncLauncher mLauncher;
    private MockReceiver mLauncherServiceReceiver;

    private SharedPreferences mPrefs;

    static class MockReceiver extends BackgroundSyncLauncherService.Receiver {
        private boolean mIsOnline = true;
        private boolean mDidStartService;

        public void setOnline(boolean online) {
            mIsOnline = online;
        }

        @Override
        protected boolean isOnline(Context context) {
            return mIsOnline;
        }

        @Override
        protected void startService(Context context) {
            startServiceImpl();
        }

        private void startServiceImpl() {
            mDidStartService = true;
        }

        protected void checkExpectations(boolean expectedStartService) {
            assertEquals("StartedService", expectedStartService, mDidStartService);
        }
    }

    @Override
    protected void setUp() throws Exception {
        mContext = new AdvancedMockContext(getInstrumentation().getTargetContext());
        mLauncher = BackgroundSyncLauncher.create(mContext);
        mLauncherServiceReceiver = new MockReceiver();

        mPrefs = mContext.getSharedPreferences(
                mContext.getPackageName() + "_preferences", Context.MODE_PRIVATE);
    }

    private void deleteLauncherInstance() {
        mLauncher.destroy();
        mLauncher = null;
    }

    private void startOnReceiveAndVerify(boolean shouldStart) {
        mLauncherServiceReceiver.onReceive(
                mContext, new Intent(ConnectivityManager.CONNECTIVITY_ACTION));
        mLauncherServiceReceiver.checkExpectations(shouldStart);
    }

    @SmallTest
    @Feature({"BackgroundSync"})
    public void testHasInstance() {
        assertTrue(BackgroundSyncLauncher.hasInstance());
        mLauncher.destroy();
        assertFalse(BackgroundSyncLauncher.hasInstance());
    }

    @SmallTest
    @Feature({"BackgroundSync"})
    public void testDefaultNoLaunch() {
        assertFalse(BackgroundSyncLauncher.shouldLaunchWhenNextOnline(mPrefs));
    }

    @SmallTest
    @Feature({"BackgroundSync"})
    public void testSetLaunchWhenNextOnline() {
        assertFalse(BackgroundSyncLauncher.shouldLaunchWhenNextOnline(mPrefs));
        mLauncher.setLaunchWhenNextOnline(true);
        assertTrue(BackgroundSyncLauncher.shouldLaunchWhenNextOnline(mPrefs));
        mLauncher.setLaunchWhenNextOnline(false);
        assertFalse(BackgroundSyncLauncher.shouldLaunchWhenNextOnline(mPrefs));
    }

    @SmallTest
    @Feature({"BackgroundSync"})
    public void testNewLauncherDisablesNextOnline() {
        mLauncher.setLaunchWhenNextOnline(true);
        assertTrue(BackgroundSyncLauncher.shouldLaunchWhenNextOnline(mPrefs));

        // Simulate restarting the browser by deleting the launcher and creating a new one.
        deleteLauncherInstance();
        mLauncher = BackgroundSyncLauncher.create(mContext);
        assertFalse(BackgroundSyncLauncher.shouldLaunchWhenNextOnline(mPrefs));
    }

    @SmallTest
    @Feature({"BackgroundSync"})
    public void testFireWhenScheduled() {
        mLauncher.setLaunchWhenNextOnline(true);
        deleteLauncherInstance();

        mLauncherServiceReceiver.setOnline(true);
        startOnReceiveAndVerify(true);
    }

    @SmallTest
    @Feature({"BackgroundSync"})
    public void testNoFireWhenNotScheduled() {
        mLauncher.setLaunchWhenNextOnline(false);
        deleteLauncherInstance();

        mLauncherServiceReceiver.setOnline(true);
        startOnReceiveAndVerify(false);
    }

    @SmallTest
    @Feature({"BackgroundSync"})
    public void testNoFireWhenInstanceExists() {
        mLauncher.setLaunchWhenNextOnline(true);
        mLauncherServiceReceiver.setOnline(true);
        startOnReceiveAndVerify(false);

        deleteLauncherInstance();
        startOnReceiveAndVerify(true);
    }

    @SmallTest
    @Feature({"BackgroundSync"})
    public void testReceiverOffline() {
        mLauncher.setLaunchWhenNextOnline(true);
        mLauncherServiceReceiver.setOnline(false);
        deleteLauncherInstance();
        startOnReceiveAndVerify(false);
    }

    @SmallTest
    @Feature({"BackgroundSync"})
    public void testReceiverOnline() {
        mLauncher.setLaunchWhenNextOnline(true);
        mLauncherServiceReceiver.setOnline(true);
        deleteLauncherInstance();
        startOnReceiveAndVerify(true);
    }

    @SmallTest
    @Feature({"BackgroundSync"})
    public void testStartingService() {
        Intent serviceIntent = new Intent(mContext, BackgroundSyncLauncherService.class);
        MockReceiver.startWakefulService(mContext, serviceIntent);
    }
}
