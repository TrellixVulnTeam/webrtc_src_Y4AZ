// Copyright 2015 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/proximity_auth/cryptauth/cryptauth_device_manager.h"

#include "base/prefs/pref_registry_simple.h"
#include "base/prefs/pref_service.h"
#include "base/prefs/scoped_user_pref_update.h"
#include "components/proximity_auth/cryptauth/cryptauth_client.h"
#include "components/proximity_auth/cryptauth/pref_names.h"
#include "components/proximity_auth/cryptauth/sync_scheduler_impl.h"
#include "components/proximity_auth/logging/logging.h"

namespace proximity_auth {

namespace {

// The normal period between successful syncs, in hours.
const int kRefreshPeriodHours = 24;

// A more aggressive period between sync attempts to recover when the last
// sync attempt fails, in minutes. This is a base time that increases for each
// subsequent failure.
const int kDeviceSyncBaseRecoveryPeriodMinutes = 10;

// The bound on the amount to jitter the period between syncs.
const double kDeviceSyncMaxJitterRatio = 0.2;

// Keys for ExternalDeviceInfo dictionaries that are stored in the user's prefs.
const char kExternalDeviceKeyPublicKey[] = "public_key";
const char kExternalDeviceKeyDeviceName[] = "device_name";
const char kExternalDeviceKeyBluetoothAddress[] = "bluetooth_address";

// Converts an unlock key proto to a dictionary that can be stored in user
// prefs.
scoped_ptr<base::DictionaryValue> UnlockKeyToDictionary(
    const cryptauth::ExternalDeviceInfo& device) {
  scoped_ptr<base::DictionaryValue> dictionary(new base::DictionaryValue());
  dictionary->SetString(kExternalDeviceKeyPublicKey, device.public_key());
  dictionary->SetString(kExternalDeviceKeyDeviceName,
                        device.friendly_device_name());
  dictionary->SetString(kExternalDeviceKeyBluetoothAddress,
                        device.bluetooth_address());
  return dictionary.Pass();
}

// Converts an unlock key dictionary stored in user prefs to an
// ExternalDeviceInfo proto. Returns true if the dictionary is valid, and the
// parsed proto is written to |external_device|.
bool DictionaryToUnlockKey(const base::DictionaryValue& dictionary,
                           cryptauth::ExternalDeviceInfo* external_device) {
  std::string public_key, device_name, bluetooth_address;
  if (!dictionary.GetString(kExternalDeviceKeyPublicKey, &public_key) ||
      !dictionary.GetString(kExternalDeviceKeyDeviceName, &device_name) ||
      !dictionary.GetString(kExternalDeviceKeyBluetoothAddress,
                            &bluetooth_address)) {
    return false;
  }

  external_device->set_public_key(public_key);
  external_device->set_friendly_device_name(device_name);
  external_device->set_bluetooth_address(bluetooth_address);
  external_device->set_unlock_key(true);
  external_device->set_unlockable(false);
  return true;
}

}  // namespace

CryptAuthDeviceManager::CryptAuthDeviceManager(
    scoped_ptr<base::Clock> clock,
    scoped_ptr<CryptAuthClientFactory> client_factory,
    PrefService* pref_service)
    : clock_(clock.Pass()),
      client_factory_(client_factory.Pass()),
      pref_service_(pref_service),
      weak_ptr_factory_(this) {
}

CryptAuthDeviceManager::~CryptAuthDeviceManager() {
}

// static
void CryptAuthDeviceManager::RegisterPrefs(PrefRegistrySimple* registry) {
  registry->RegisterDoublePref(prefs::kCryptAuthDeviceSyncLastSyncTimeSeconds,
                               0.0);
  registry->RegisterBooleanPref(
      prefs::kCryptAuthDeviceSyncIsRecoveringFromFailure, false);
  registry->RegisterIntegerPref(prefs::kCryptAuthDeviceSyncReason,
                                cryptauth::INVOCATION_REASON_UNKNOWN);
  registry->RegisterListPref(prefs::kCryptAuthDeviceSyncUnlockKeys);
}

void CryptAuthDeviceManager::Start() {
  UpdateUnlockKeysFromPrefs();

  base::Time last_successful_sync = GetLastSyncTime();
  base::TimeDelta elapsed_time_since_last_sync =
      clock_->Now() - last_successful_sync;

  bool is_recovering_from_failure =
      pref_service_->GetBoolean(
          prefs::kCryptAuthDeviceSyncIsRecoveringFromFailure) ||
      last_successful_sync.is_null();

  scheduler_ = CreateSyncScheduler();
  scheduler_->Start(elapsed_time_since_last_sync,
                    is_recovering_from_failure
                        ? SyncScheduler::Strategy::AGGRESSIVE_RECOVERY
                        : SyncScheduler::Strategy::PERIODIC_REFRESH);
}

void CryptAuthDeviceManager::AddObserver(Observer* observer) {
  observers_.AddObserver(observer);
}

void CryptAuthDeviceManager::RemoveObserver(Observer* observer) {
  observers_.RemoveObserver(observer);
}

void CryptAuthDeviceManager::ForceSyncNow(
    cryptauth::InvocationReason invocation_reason) {
  pref_service_->SetInteger(prefs::kCryptAuthDeviceSyncReason,
                            invocation_reason);
  scheduler_->ForceSync();
}

base::Time CryptAuthDeviceManager::GetLastSyncTime() const {
  return base::Time::FromDoubleT(
      pref_service_->GetDouble(prefs::kCryptAuthDeviceSyncLastSyncTimeSeconds));
}

base::TimeDelta CryptAuthDeviceManager::GetTimeToNextAttempt() const {
  return scheduler_->GetTimeToNextSync();
}

bool CryptAuthDeviceManager::IsSyncInProgress() const {
  return scheduler_->GetSyncState() ==
         SyncScheduler::SyncState::SYNC_IN_PROGRESS;
}

bool CryptAuthDeviceManager::IsRecoveringFromFailure() const {
  return scheduler_->GetStrategy() ==
         SyncScheduler::Strategy::AGGRESSIVE_RECOVERY;
}

void CryptAuthDeviceManager::OnGetMyDevicesSuccess(
    const cryptauth::GetMyDevicesResponse& response) {
  // Update the unlock keys stored in the user's prefs.
  scoped_ptr<base::ListValue> unlock_keys_pref(new base::ListValue());
  for (const auto& device : response.devices()) {
    if (device.unlock_key())
      unlock_keys_pref->Append(UnlockKeyToDictionary(device));
  }

  bool unlock_keys_changed = !unlock_keys_pref->Equals(
      pref_service_->GetList(prefs::kCryptAuthDeviceSyncUnlockKeys));
  {
    ListPrefUpdate update(pref_service_, prefs::kCryptAuthDeviceSyncUnlockKeys);
    update.Get()->Swap(unlock_keys_pref.get());
  }
  UpdateUnlockKeysFromPrefs();

  // Reset metadata used for scheduling syncing.
  pref_service_->SetBoolean(prefs::kCryptAuthDeviceSyncIsRecoveringFromFailure,
                            false);
  pref_service_->SetDouble(prefs::kCryptAuthDeviceSyncLastSyncTimeSeconds,
                           clock_->Now().ToDoubleT());
  pref_service_->SetInteger(prefs::kCryptAuthDeviceSyncReason,
                            cryptauth::INVOCATION_REASON_UNKNOWN);

  sync_request_->OnDidComplete(true);
  cryptauth_client_.reset();
  sync_request_.reset();
  FOR_EACH_OBSERVER(
      Observer, observers_,
      OnSyncFinished(SyncResult::SUCCESS, unlock_keys_changed
                                              ? DeviceChangeResult::CHANGED
                                              : DeviceChangeResult::UNCHANGED));
}

void CryptAuthDeviceManager::OnGetMyDevicesFailure(const std::string& error) {
  PA_LOG(ERROR) << "GetMyDevices API failed: " << error;
  pref_service_->SetBoolean(prefs::kCryptAuthDeviceSyncIsRecoveringFromFailure,
                            true);
  sync_request_->OnDidComplete(false);
  cryptauth_client_.reset();
  sync_request_.reset();
  FOR_EACH_OBSERVER(
      Observer, observers_,
      OnSyncFinished(SyncResult::FAILURE, DeviceChangeResult::UNCHANGED));
}

scoped_ptr<SyncScheduler> CryptAuthDeviceManager::CreateSyncScheduler() {
  return make_scoped_ptr(new SyncSchedulerImpl(
      this, base::TimeDelta::FromHours(kRefreshPeriodHours),
      base::TimeDelta::FromMinutes(kDeviceSyncBaseRecoveryPeriodMinutes),
      kDeviceSyncMaxJitterRatio, "CryptAuth DeviceSync"));
}

void CryptAuthDeviceManager::UpdateUnlockKeysFromPrefs() {
  const base::ListValue* unlock_key_list =
      pref_service_->GetList(prefs::kCryptAuthDeviceSyncUnlockKeys);
  unlock_keys_.clear();
  for (size_t i = 0; i < unlock_key_list->GetSize(); ++i) {
    const base::DictionaryValue* unlock_key_dictionary;
    if (unlock_key_list->GetDictionary(i, &unlock_key_dictionary)) {
      cryptauth::ExternalDeviceInfo unlock_key;
      if (DictionaryToUnlockKey(*unlock_key_dictionary, &unlock_key)) {
        unlock_keys_.push_back(unlock_key);
      } else {
        PA_LOG(ERROR) << "Unable to deserialize unlock key dictionary "
                      << "(index=" << i << "):\n" << *unlock_key_dictionary;
      }
    } else {
      PA_LOG(ERROR) << "Can not get dictionary in list of unlock keys "
                    << "(index=" << i << "):\n" << *unlock_key_list;
    }
  }
}

void CryptAuthDeviceManager::OnSyncRequested(
    scoped_ptr<SyncScheduler::SyncRequest> sync_request) {
  FOR_EACH_OBSERVER(Observer, observers_, OnSyncStarted());

  sync_request_ = sync_request.Pass();
  cryptauth_client_ = client_factory_->CreateInstance();

  cryptauth::InvocationReason invocation_reason =
      cryptauth::INVOCATION_REASON_UNKNOWN;

  int reason_stored_in_prefs =
      pref_service_->GetInteger(prefs::kCryptAuthDeviceSyncReason);

  if (cryptauth::InvocationReason_IsValid(reason_stored_in_prefs) &&
      reason_stored_in_prefs != cryptauth::INVOCATION_REASON_UNKNOWN) {
    invocation_reason =
        static_cast<cryptauth::InvocationReason>(reason_stored_in_prefs);
  } else if (GetLastSyncTime().is_null()) {
    invocation_reason = cryptauth::INVOCATION_REASON_INITIALIZATION;
  } else if (IsRecoveringFromFailure()) {
    invocation_reason = cryptauth::INVOCATION_REASON_FAILURE_RECOVERY;
  } else {
    invocation_reason = cryptauth::INVOCATION_REASON_PERIODIC;
  }

  cryptauth::GetMyDevicesRequest request;
  request.set_invocation_reason(invocation_reason);
  cryptauth_client_->GetMyDevices(
      request, base::Bind(&CryptAuthDeviceManager::OnGetMyDevicesSuccess,
                          weak_ptr_factory_.GetWeakPtr()),
      base::Bind(&CryptAuthDeviceManager::OnGetMyDevicesFailure,
                 weak_ptr_factory_.GetWeakPtr()));
}

}  // namespace proximity_auth
