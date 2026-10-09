import {
  CognitoUserPool,
  CognitoUser,
  AuthenticationDetails
} from 'amazon-cognito-identity-js';

const config = window.APP_CONFIG;

if (!config?.userPoolId || !config?.clientId) {
  throw new Error('Cognito configuration is missing. Check public/config.js');
}

const userPool = new CognitoUserPool({
  UserPoolId: config.userPoolId,
  ClientId: config.clientId
});

export function signUp(email, password) {
  return new Promise((resolve, reject) => {
    userPool.signUp(email, password, [], [], (error, result) => {
      if (error) reject(error);
      else resolve(result);
    });
  });
}

export function confirmSignUp(email, code) {
  return new Promise((resolve, reject) => {
    const user = new CognitoUser({ Username: email, Pool: userPool });

    user.confirmRegistration(code, true, (error, result) => {
      if (error) reject(error);
      else resolve(result);
    });
  });
}

export function signIn(email, password) {
  return new Promise((resolve, reject) => {
    const user = new CognitoUser({ Username: email, Pool: userPool });
    const details = new AuthenticationDetails({
      Username: email,
      Password: password
    });

    user.authenticateUser(details, {
      onSuccess: resolve,
      onFailure: reject
    });
  });
}

export function signOut() {
  userPool.getCurrentUser()?.signOut();
}

export function getIdToken() {
  return new Promise((resolve, reject) => {
    const user = userPool.getCurrentUser();

    if (!user) {
      reject(new Error('Please sign in first.'));
      return;
    }

    user.getSession((error, session) => {
      if (error) {
        reject(error);
        return;
      }

      if (!session?.isValid()) {
        reject(new Error('Your session has expired. Please sign in again.'));
        return;
      }

      resolve(session.getIdToken().getJwtToken());
    });
  });
}

export function getCurrentUser() {
  return userPool.getCurrentUser();
}
