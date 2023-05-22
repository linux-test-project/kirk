pipeline {
  agent {
    node {
      label "kirk"
    }
  }
  environment {
    TEST_QEMU_IMAGE    = "/data/image.qcow2"
    TEST_QEMU_PASSWORD = "root"
    TEST_SSH_USERNAME  = "auto"
    TEST_SSH_PASSWORD  = "auto1234"
    TEST_SSH_KEY_FILE  = "/data/jenkins_rsa"
    TEST_LTX_BINARY  = "/data/ltx"
  }
  stages {
    stage("Test host") {
      steps {
        catchError(buildResult: 'SUCCESS', stageResult: 'FAILURE') {
          sh 'coverage run -a -m pytest -m "not qemu and not ssh" --junit-xml=results-host.xml'
        }
      }
    }
    stage("Test SSH") {
      steps {
        catchError(buildResult: 'SUCCESS', stageResult: 'FAILURE') {
          sh 'coverage run -a -m pytest -m "ssh" --junit-xml=results-ssh.xml'
        }
      }
    }
    stage("Test Qemu") {
      steps {
        catchError(buildResult: 'SUCCESS', stageResult: 'FAILURE') {
          sh 'coverage run -a -m pytest -m "qemu" --junit-xml=results-qemu.xml'
        }
      }
    }
    stage("Test LTX") {
      steps {
        catchError(buildResult: 'SUCCESS', stageResult: 'FAILURE') {
          sh 'coverage run -a -m pytest -m "ltx" --junit-xml=results-ltx.xml'
        }
      }
    }
  }
  post {
    always {
      sh 'coverage xml -o coverage.xml'
      cobertura coberturaReportFile: 'coverage.xml'
      junit 'results-*.xml'
    }
  }
}