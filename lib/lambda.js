'use strict'

const awsSdk = require('aws-sdk')

const trigger = async (s3Key, debug) => {
  const logger = debug === true ? console.dir : _ => {}

  const lambdaClient = new awsSdk.Lambda({
    apiVersion: '2015-03-31',
    region: 'us-east-1'
  })

  const lambdaParams = {
    ClientContext: '',
    FunctionName: 'brave-redirection-analyser',
    InvocationType: 'Event',
    Payload: {
      database: 'com-brave-research-redirections.cdbhbp7bfc4z.us-east-1.neptune.amazonaws.com',
      key: s3Key,
      debug
    }
  }
  logger(`Calling ${lambdaParams.FunctionName} with args ${JSON.stringify(lambdaParams.Payload)}.`)

  lambdaParams.Payload = JSON.stringify(lambdaParams.Payload)

  return lambdaClient.invoke(lambdaParams).promise()
}

module.exports.trigger = trigger
