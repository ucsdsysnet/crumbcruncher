'use strict'

const zlib = require('zlib')

const uuidv4 = require('uuid/v4')
const awsSdk = require('aws-sdk')

const urlsLib = require('./urls')

const globalS3 = new awsSdk.S3({
  apiVersion: '2006-03-01',
  region: 'us-east-1'
})

const record = async (url, bucketName, data, debug) => {
  const logger = debug === true ? console.dir : _ => {}

  const domain = urlsLib.getDomain(url)
  const crawlId = uuidv4()
  const key = `${domain}_${crawlId}.json.gz`

  const dataBuffer = Buffer.from(JSON.stringify(data))

  const compressedBuffer = zlib.gzipSync(dataBuffer, 'utf8')

  const s3Params = {
    Body: compressedBuffer,
    Bucket: bucketName,
    Key: key
  }

  logger(`sending ${key} to S3.`)
  await globalS3.putObject(s3Params).promise()

  return key
}

module.exports.record = record
