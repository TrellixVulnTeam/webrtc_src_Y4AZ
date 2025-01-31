// Copyright 2015 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

package org.chromium.chrome.browser.sync.ui;

import android.accounts.Account;
import android.accounts.AccountManager;
import android.accounts.AccountManagerCallback;
import android.accounts.AccountManagerFuture;
import android.accounts.AuthenticatorException;
import android.accounts.OperationCanceledException;
import android.app.Activity;
import android.app.DialogFragment;
import android.app.FragmentTransaction;
import android.content.Intent;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.preference.CheckBoxPreference;
import android.preference.Preference;
import android.preference.Preference.OnPreferenceChangeListener;
import android.preference.Preference.OnPreferenceClickListener;
import android.preference.PreferenceFragment;
import android.preference.SwitchPreference;
import android.text.Spannable;
import android.text.SpannableString;
import android.text.style.ForegroundColorSpan;
import android.util.Log;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;

import org.chromium.base.VisibleForTesting;
import org.chromium.chrome.R;
import org.chromium.chrome.browser.childaccounts.ChildAccountService;
import org.chromium.chrome.browser.invalidation.InvalidationController;
import org.chromium.chrome.browser.preferences.ChromeSwitchPreference;
import org.chromium.chrome.browser.sync.ProfileSyncService;
import org.chromium.chrome.browser.sync.SyncController;
import org.chromium.sync.AndroidSyncSettings;
import org.chromium.sync.internal_api.pub.PassphraseType;
import org.chromium.sync.internal_api.pub.base.ModelType;
import org.chromium.sync.signin.AccountManagerHelper;

import java.io.IOException;
import java.util.HashSet;
import java.util.Set;

/**
 * Settings fragment to customize Sync options (data types, encryption).
 */
public class SyncCustomizationFragment extends PreferenceFragment implements
        PassphraseDialogFragment.Listener, PassphraseTypeDialogFragment.Listener,
        OnPreferenceClickListener, OnPreferenceChangeListener,
        ProfileSyncService.SyncStateChangedListener {

    private static final String TAG = "SyncCustomizationFragment";

    @VisibleForTesting
    public static final String FRAGMENT_ENTER_PASSWORD = "enter_password";
    @VisibleForTesting
    public static final String FRAGMENT_CUSTOM_PASSWORD = "custom_password";
    @VisibleForTesting
    public static final String FRAGMENT_PASSWORD_TYPE = "password_type";

    @VisibleForTesting
    public static final String PREFERENCE_SYNC_EVERYTHING = "sync_everything";
    @VisibleForTesting
    public static final String PREFERENCE_SYNC_AUTOFILL = "sync_autofill";
    @VisibleForTesting
    public static final String PREFERENCE_SYNC_BOOKMARKS = "sync_bookmarks";
    @VisibleForTesting
    public static final String PREFERENCE_SYNC_OMNIBOX = "sync_omnibox";
    @VisibleForTesting
    public static final String PREFERENCE_SYNC_PASSWORDS = "sync_passwords";
    @VisibleForTesting
    public static final String PREFERENCE_SYNC_RECENT_TABS = "sync_recent_tabs";
    @VisibleForTesting
    public static final String PREFERENCE_ENCRYPTION = "encryption";
    @VisibleForTesting
    public static final String PREF_SYNC_SWITCH = "sync_switch";
    @VisibleForTesting
    public static final String PREFERENCE_SYNC_MANAGE_DATA = "sync_manage_data";

    public static final String ARGUMENT_ACCOUNT = "account";

    private static final int ERROR_COLOR = Color.RED;

    private ChromeSwitchPreference mSyncSwitchPreference;
    private boolean mIsSyncInitialized;

    @VisibleForTesting
    public static final String[] PREFS_TO_SAVE = {
        PREFERENCE_SYNC_EVERYTHING,
        PREFERENCE_SYNC_AUTOFILL,
        PREFERENCE_SYNC_BOOKMARKS,
        PREFERENCE_SYNC_OMNIBOX,
        PREFERENCE_SYNC_PASSWORDS,
        PREFERENCE_SYNC_RECENT_TABS,
    };

    private static final String DASHBOARD_URL = "https://www.google.com/settings/chrome/sync";

    private SwitchPreference mSyncEverything;
    private CheckBoxPreference mSyncAutofill;
    private CheckBoxPreference mSyncBookmarks;
    private CheckBoxPreference mSyncOmnibox;
    private CheckBoxPreference mSyncPasswords;
    private CheckBoxPreference mSyncRecentTabs;
    private Preference mSyncEncryption;
    private Preference mManageSyncData;
    private CheckBoxPreference[] mAllTypes;
    private boolean mCheckboxesInitialized;

    private ProfileSyncService mProfileSyncService;

    @Override
    public View onCreateView(LayoutInflater inflater, ViewGroup container,
                             Bundle savedInstanceState) {
        mProfileSyncService = ProfileSyncService.get(getActivity());
        mIsSyncInitialized = mProfileSyncService.isSyncInitialized();

        getActivity().setTitle(R.string.sign_in_sync);

        View view = super.onCreateView(inflater, container, savedInstanceState);
        addPreferencesFromResource(R.xml.sync_customization_preferences);
        mSyncEverything = (SwitchPreference) findPreference(PREFERENCE_SYNC_EVERYTHING);
        mSyncAutofill = (CheckBoxPreference) findPreference(PREFERENCE_SYNC_AUTOFILL);
        mSyncBookmarks = (CheckBoxPreference) findPreference(PREFERENCE_SYNC_BOOKMARKS);
        mSyncOmnibox = (CheckBoxPreference) findPreference(PREFERENCE_SYNC_OMNIBOX);
        mSyncPasswords = (CheckBoxPreference) findPreference(PREFERENCE_SYNC_PASSWORDS);
        mSyncRecentTabs = (CheckBoxPreference) findPreference(PREFERENCE_SYNC_RECENT_TABS);
        mSyncEncryption = findPreference(PREFERENCE_ENCRYPTION);
        mSyncEncryption.setOnPreferenceClickListener(this);
        mManageSyncData = findPreference(PREFERENCE_SYNC_MANAGE_DATA);
        mManageSyncData.setOnPreferenceClickListener(this);

        mAllTypes = new CheckBoxPreference[]{
            mSyncAutofill, mSyncBookmarks, mSyncOmnibox, mSyncPasswords, mSyncRecentTabs,
        };

        mSyncEverything.setOnPreferenceChangeListener(this);
        for (CheckBoxPreference type : mAllTypes) {
            type.setOnPreferenceChangeListener(this);
        }

        mSyncSwitchPreference = (ChromeSwitchPreference) findPreference(PREF_SYNC_SWITCH);
        mSyncSwitchPreference.setOnPreferenceChangeListener(new OnPreferenceChangeListener() {
            @Override
            public boolean onPreferenceChange(Preference preference, Object newValue) {
                assert canDisableSync();
                SyncController syncController = SyncController.get(getActivity());
                if ((boolean) newValue) {
                    syncController.start();
                } else {
                    syncController.stop();
                }
                // Must be done asynchronously because the switch state isn't updated
                // until after this function exits.
                new Handler().post(new Runnable() {
                    @Override
                    public void run() {
                        updateSyncStateFromSwitch();
                    }
                });
                return true;
            }
        });

        return view;
    }

    @Override
    public boolean onPreferenceChange(Preference preference, Object newValue) {
        if (preference == mSyncEverything) {
            new Handler().post(new Runnable() {
                @Override
                public void run() {
                    updateDataTypeState();
                }
            });
            return true;
        }
        if (isSyncTypePreference(preference)) {
            new Handler().post(new Runnable() {
                @Override
                public void run() {
                    maybeDisableSync();
                }
            });
            return true;
        }
        return false;
    }

    /**
     * @return Whether Sync can be disabled.
     */
    private boolean canDisableSync() {
        return !ChildAccountService.getInstance(getActivity()).hasChildAccount();
    }

    private boolean isSyncTypePreference(Preference preference) {
        for (Preference pref : mAllTypes) {
            if (pref == preference) return true;
        }
        return false;
    }

    /**
     * Returns the sync action bar switch to enable/disable sync.
     *
     * @return the mActionBarSwitch
     */
    @VisibleForTesting
    public ChromeSwitchPreference getSyncSwitchPreference() {
        return mSyncSwitchPreference;
    }

    @Override
    public void onResume() {
        super.onResume();
        mIsSyncInitialized = mProfileSyncService.isSyncInitialized();
        // This prevents sync from actually syncing until the dialog is closed.
        mProfileSyncService.setSetupInProgress(true);
        mProfileSyncService.addSyncStateChangedListener(this);
        updateSyncState();
    }

    @Override
    public void onPause() {
        super.onPause();
        mProfileSyncService.removeSyncStateChangedListener(this);
        // If this activity is closing, apply configuration changes and tell sync that
        // the user is done configuring sync.
        if (!getActivity().isChangingConfigurations()) {
            // Only save state if the switch and external state match. If a stop and clear comes
            // while the dialog is open, this will be false and settings won't be saved.
            if (mSyncSwitchPreference.isChecked()
                    && AndroidSyncSettings.isSyncEnabled(getActivity())) {
                // Save the new data type state.
                configureSyncDataTypes();
                // Inform sync that the user has finished setting up sync at least once.
                mProfileSyncService.setSyncSetupCompleted();
            }
            // Setup is done. This was preventing sync from turning on even if it was enabled.
            mProfileSyncService.setSetupInProgress(false);
        }
    }

    /**
     * Update the state of all settings from sync.
     *
     * This sets the state of the sync switch from external sync state and then calls
     * updateSyncStateFromSwitch, which uses that as its source of truth.
     */
    private void updateSyncState() {
        boolean isSyncEnabled = AndroidSyncSettings.isSyncEnabled(getActivity());
        mSyncSwitchPreference.setChecked(isSyncEnabled);
        mSyncSwitchPreference.setEnabled(canDisableSync());
        updateSyncStateFromSwitch();
    }

    /**
     * Update the state of settings using the switch state to determine if sync is enabled.
     */
    private void updateSyncStateFromSwitch() {
        updateSyncEverythingState();
        updateDataTypeState();
        updateEncryptionState();
    }

    /**
     * Update the encryption state.
     *
     * If sync's backend is initialized, the button is enabled and the dialog will present the
     * valid encryption options for the user. Otherwise, any encryption dialogs will be closed
     * and the button will be disabled because the backend is needed in order to know and
     * modify the encryption state.
     */
    private void updateEncryptionState() {
        boolean isSyncEnabled = mSyncSwitchPreference.isChecked();
        boolean isSyncInitialized = mProfileSyncService.isSyncInitialized();
        mSyncEncryption.setEnabled(isSyncEnabled && isSyncInitialized);
        mSyncEncryption.setSummary(null);
        if (!isSyncInitialized) {
            // If sync is not initialized, encryption state is unavailable and can't be changed.
            // Leave the button disabled and the summary empty. Additionally, close the dialogs in
            // case they were open when a stop and clear comes.
            closeDialogIfOpen(FRAGMENT_CUSTOM_PASSWORD);
            closeDialogIfOpen(FRAGMENT_ENTER_PASSWORD);
            return;
        }
        if (mProfileSyncService.isPassphraseRequiredForDecryption() && isAdded()) {
            mSyncEncryption.setSummary(
                    errorSummary(getString(R.string.sync_need_passphrase)));
        }
    }

    /**
     * Applies a span to the given string to give it an error color.
     */
    private static Spannable errorSummary(String string) {
        SpannableString summary = new SpannableString(string);
        summary.setSpan(new ForegroundColorSpan(ERROR_COLOR), 0, summary.length(), 0);
        return summary;
    }

    private void configureSyncDataTypes() {
        if (maybeDisableSync()) return;

        boolean syncEverything = mSyncEverything.isChecked();
        mProfileSyncService.setPreferredDataTypes(syncEverything, getSelectedModelTypes());
        // Update the invalidation listener with the set of types we are enabling.
        InvalidationController invController =
                InvalidationController.get(getActivity());
        invController.ensureStartedAndUpdateRegisteredTypes();
    }

    private Set<ModelType> getSelectedModelTypes() {
        Set<ModelType> types = new HashSet<ModelType>();
        if (mSyncAutofill.isChecked()) types.add(ModelType.AUTOFILL);
        if (mSyncBookmarks.isChecked()) types.add(ModelType.BOOKMARK);
        if (mSyncOmnibox.isChecked()) types.add(ModelType.TYPED_URL);
        if (mSyncPasswords.isChecked()) types.add(ModelType.PASSWORD);
        if (mSyncRecentTabs.isChecked()) types.add(ModelType.PROXY_TABS);
        return types;
    }

    private void displayPasswordTypeDialog() {
        FragmentTransaction ft = getFragmentManager().beginTransaction();
        PassphraseTypeDialogFragment dialog = PassphraseTypeDialogFragment.create(
                mProfileSyncService.getPassphraseType(),
                mProfileSyncService.getExplicitPassphraseTime(),
                mProfileSyncService.isEncryptEverythingAllowed());
        dialog.show(ft, FRAGMENT_PASSWORD_TYPE);
        dialog.setTargetFragment(this, -1);
    }

    private void displayPasswordDialog(boolean isGaia, boolean isUpdate) {
        FragmentTransaction ft = getFragmentManager().beginTransaction();
        PassphraseDialogFragment.newInstance(this, isGaia, isUpdate)
                .show(ft, FRAGMENT_ENTER_PASSWORD);
    }

    private void displayCustomPasswordDialog() {
        FragmentTransaction ft = getFragmentManager().beginTransaction();
        PassphraseCreationDialogFragment dialog = new PassphraseCreationDialogFragment();
        dialog.setTargetFragment(this, -1);
        dialog.show(ft, FRAGMENT_CUSTOM_PASSWORD);
    }

    private void closeDialogIfOpen(String tag) {
        DialogFragment df = (DialogFragment) getFragmentManager().findFragmentByTag(tag);
        if (df != null) {
            df.dismiss();
        }
    }

    private void configureEncryption(String passphrase, boolean isGaia) {
        if (mProfileSyncService.isSyncInitialized()) {
            mProfileSyncService.enableEncryptEverything();
            mProfileSyncService.setEncryptionPassphrase(passphrase, isGaia);
            // Configure the current set of data types - this tells the sync engine to
            // apply our encryption configuration changes.
            configureSyncDataTypes();
            // Re-display our config UI to properly reflect the new state.
            updateSyncState();
        }
    }

    private void handleEncryptWithGaia(final String passphrase) {
        AccountManager accountManager = (AccountManager) getActivity().getSystemService(
                Activity.ACCOUNT_SERVICE);
        String username = getArguments().getString(ARGUMENT_ACCOUNT);
        AccountManagerCallback<Bundle> callback = new AccountManagerCallback<Bundle>() {
            @Override
            public void run(AccountManagerFuture<Bundle> future) {
                boolean validPassword = false;
                try {
                    Bundle result = future.getResult();
                    validPassword = result.getBoolean(AccountManager.KEY_BOOLEAN_RESULT);
                } catch (OperationCanceledException e) {
                    // TODO(jgreenwald): notify user that we're unable to
                    // validate passphrase?
                    Log.e(TAG, "unable to verify password", e);
                } catch (AuthenticatorException e) {
                    Log.e(TAG, "unable to verify password", e);
                } catch (IOException e) {
                    Log.e(TAG, "unable to verify password", e);
                }

                Log.d(TAG, "GAIA password valid: " + validPassword);
                if (validPassword) {
                    configureEncryption(passphrase, true);
                } else {
                    notifyInvalidPassphrase();
                }
            }
        };
        Account account = AccountManagerHelper.createAccountFromName(username);
        Bundle options = new Bundle();
        options.putString(AccountManager.KEY_PASSWORD, passphrase);
        accountManager.confirmCredentials(account, options, null, callback, null);
    }

    private void handleEncryptWithCustomPassphrase(String passphrase) {
        configureEncryption(passphrase, false);
    }

    /**
     * @return whether the passphrase successfully decrypted the pending keys.
     */
    private boolean handleDecryption(String passphrase) {
        if (!passphrase.isEmpty() && mProfileSyncService.setDecryptionPassphrase(passphrase)) {
            // PassphraseDialogFragment doesn't handle closing itself, so do it here. This is
            // not done in updateSyncState() because that happens onResume and possibly in other
            // cases where the dialog should stay open.
            closeDialogIfOpen(FRAGMENT_ENTER_PASSWORD);
            // Update our configuration UI.
            updateSyncState();
            return true;
        } else {
            // Let the user know that the passphrase was not valid.
            notifyInvalidPassphrase();
            return false;
        }
    }

    /**
     * Callback for PassphraseDialogFragment.Listener
     */
    @Override
    public boolean onPassphraseEntered(String passphrase, boolean isGaia, boolean isUpdate) {
        if (isUpdate) {
            handleEncryptWithCustomPassphrase(passphrase);
            // Setting a new passphrase should always succeed (validation that
            // it's not an empty passphrase should already have happened).
            return true;
        } else {
            return handleDecryption(passphrase);
        }
    }

    private void notifyInvalidPassphrase() {
        PassphraseDialogFragment passwordDialog = (PassphraseDialogFragment)
                getFragmentManager().findFragmentByTag(FRAGMENT_ENTER_PASSWORD);
        if (passwordDialog != null) {
            passwordDialog.invalidPassphrase();
        } else {
            Log.w(TAG, "invalid passphrase but no dialog to notify");
        }
    }

    /**
     * Callback for PassphraseDialogFragment.Listener
     */
    @Override
    public void onPassphraseCanceled(boolean isGaia, boolean isUpdate) {
    }

    /**
     * Callback for PassphraseTypeDialogFragment.Listener
     */
    @Override
    public void onPassphraseTypeSelected(PassphraseType type) {
        boolean isAllDataEncrypted = mProfileSyncService.isEncryptEverythingEnabled();
        boolean isUsingSecondaryPassphrase = mProfileSyncService.isUsingSecondaryPassphrase();

        // The passphrase type should only ever be selected if the account doesn't have
        // full encryption enabled. Otherwise both options should be disabled.
        assert !isAllDataEncrypted;
        assert !isUsingSecondaryPassphrase;
        displayCustomPasswordDialog();
    }

    /**
     * Callback for OnPreferenceClickListener
     */
    @Override
    public boolean onPreferenceClick(Preference preference) {
        if (!isResumed()) {
            // This event could come in after onPause if the user clicks back and the preference at
            // roughly the same time.  See http://b/5983282
            return false;
        }
        if (preference == mSyncEncryption && mProfileSyncService.isSyncInitialized()) {
            if (mProfileSyncService.isPassphraseRequiredForDecryption()) {
                displayPasswordDialog(false, false);
            } else {
                displayPasswordTypeDialog();
                return true;
            }
        } else if (preference == mManageSyncData) {
            openDashboardTabInNewActivityStack();
            return true;
        }
        return false;
    }

    /**
     * Opens the Google Dashboard where the user can control the data stored for the account.
     */
    private void openDashboardTabInNewActivityStack() {
        Intent intent = new Intent(Intent.ACTION_VIEW, Uri.parse(DASHBOARD_URL));
        intent.setPackage(getActivity().getPackageName());
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        startActivity(intent);
    }

    /**
     * Update the state of the sync everything switch.
     *
     * If sync is on, load the pref from native. Otherwise display sync everything as on but
     * disable the switch.
     */
    private void updateSyncEverythingState() {
        boolean isSyncEnabled = mSyncSwitchPreference.isChecked();
        mSyncEverything.setEnabled(isSyncEnabled);
        mSyncEverything.setChecked(!isSyncEnabled
                || mProfileSyncService.hasKeepEverythingSynced());
    }

    /**
     * Update the data type switch state.
     *
     * If sync is on, load the prefs from native. Otherwise, all data types are disabled and
     * checked. Note that the Password data type will be shown as disabled and unchecked between
     * sync being turned on and the backend initialization completing.
     */
    private void updateDataTypeState() {
        boolean isSyncEnabled = mSyncSwitchPreference.isChecked();
        boolean syncEverything = mSyncEverything.isChecked();
        boolean passwordSyncConfigurable = mProfileSyncService.isSyncInitialized()
                && mProfileSyncService.isCryptographerReady();
        for (CheckBoxPreference pref : mAllTypes) {
            boolean canSyncType = pref != mSyncPasswords || passwordSyncConfigurable;

            if (!isSyncEnabled) {
                pref.setChecked(true);
            } else if (syncEverything) {
                pref.setChecked(canSyncType);
            }

            pref.setEnabled(isSyncEnabled && !syncEverything && canSyncType);
        }
        if (isSyncEnabled && !syncEverything) {
            Set<ModelType> syncTypes = mProfileSyncService.getPreferredDataTypes();
            mSyncAutofill.setChecked(syncTypes.contains(ModelType.AUTOFILL));
            mSyncBookmarks.setChecked(syncTypes.contains(ModelType.BOOKMARK));
            mSyncOmnibox.setChecked(syncTypes.contains(ModelType.TYPED_URL));
            mSyncPasswords.setChecked(passwordSyncConfigurable
                    && syncTypes.contains(ModelType.PASSWORD));
            mSyncRecentTabs.setChecked(syncTypes.contains(ModelType.PROXY_TABS));
        }
    }

    /**
     * Listen to sync state changes.
     *
     * If the user has just turned on sync, this listener is needed in order to enable
     * the encryption settings once the backend has initialized.
     */
    @Override
    public void syncStateChanged() {
        boolean wasSyncInitialized = mIsSyncInitialized;
        mIsSyncInitialized = mProfileSyncService.isSyncInitialized();
        if (mIsSyncInitialized != wasSyncInitialized) {
            // Update all because Password syncability is also affected by the backend.
            updateSyncStateFromSwitch();
        }
    }

    /**
     * Disables Sync if all data types have been disabled.
     * @return true if Sync has been disabled, false otherwise.
     */
    private boolean maybeDisableSync() {
        if (mSyncEverything.isChecked()
                || !getSelectedModelTypes().isEmpty()
                || !canDisableSync()) {
            return false;
        }
        SyncController.get(getActivity()).stop();
        mSyncSwitchPreference.setChecked(false);
        // setChecked doesn't trigger the callback, so update manually.
        updateSyncStateFromSwitch();
        return true;
    }
}
