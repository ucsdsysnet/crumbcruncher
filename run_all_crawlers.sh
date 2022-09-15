#!/bin/bash

export DISPLAY=:99

# profile_1="/home/ec2-user/.config/google-chrome/safariProfile1"
# profile_1_copy="/home/ec2-user/.config/google-chrome/safariProfile1Copy"
# profile_2="/home/ec2-user/.config/google-chrome/safariProfile2"
# chrome_profile="/home/ec2-user/.config/google-chrome/chromeProfile"

# Let's move these to make more space. Also, we need a base profile for each crawler now that we're using an extension.
base_profile_1="/data/base_profiles/safariProfile1"
base_profile_2="/data/base_profiles/safariProfile2"
base_chrome_profile="/data/base_profiles/chromeProfile"

profile_1="/data/profiles/safariProfile1"
profile_2="/data/profiles/safariProfile2"
chrome_profile="/data/profiles/chromeProfile"

echo "seeder_domain,iteration,timestamp,safariProfile1_status,safariProfile2_status,chromeProfile_status" >> /data/list_of_failed_crawls.csv

run_three_crawlers () {
    line=$1;
    ds=$2;

    # Signal the recording server to start recording this crawl
    sleep 1 # to make sure the recording server has started properly
    send_start_to_recording_server $line $ds 0

    # Run the three crawlers
    timeout -k 150s 150s node test.js "https://$line" $profile_1 $ds > /data/crawlerOutput/safariProfile1/${line}_${ds}.txt &
    pid_1=$!
    timeout -k 150s 150s node test.js "https://$line" $profile_2 $ds > /data/crawlerOutput/safariProfile2/${line}_${ds}.txt &
    pid_2=$!
    timeout -k 150s 150s node test.js "https://$line" $chrome_profile $ds > /data/crawlerOutput/chromeProfile/${line}_${ds}.txt &
    pid_3=$!

    # Wait for them to finish
    wait $pid_1
    status_1=$?
    wait $pid_2
    status_2=$?
    wait $pid_3
    status_3=$?

    # Signal the recording server to finish recording this crawl
    send_end_to_recording_server
    sleep 1 # to make sure the writing has finished

    if [[ $status_1 -gt 0 || $status_2 -gt 0 || $status_3 -gt 0 ]]; then
        echo "Crawler exited with status 1, aborting the rest of the crawls."
        # Write name of failed crawl to file: seeder_domain,iteration,timestamp, statuses
        echo "$line,0,$ds,$status_1,$status_2,$status_3" >> /data/list_of_failed_crawls.csv
        return 1
    fi
    return 0
}

run_three_crawlers_from_input_file () {
    line=$1
    ds=$2
    i=$3

    # Signal the recording server to start recording this crawl
    sleep 1 # to make sure the recording server has started properly
    send_start_to_recording_server $line $ds $i

    timeout -k 150s 150s node run_crawler_from_input_file.js $profile_1 $ds $i $line > /data/crawlerOutput/safariProfile1/${line}_${ds}_iter$i.txt &
    pid_1=$!
    timeout -k 150s 150s node run_crawler_from_input_file.js $profile_2 $ds $i $line > /data/crawlerOutput/safariProfile2/${line}_${ds}_iter$i.txt &
    pid_2=$!
    timeout -k 150s 150s node run_crawler_from_input_file.js $chrome_profile $ds $i $line > /data/crawlerOutput/chromeProfile/${line}_${ds}_iter$i.txt &
    pid_3=$!

    # Wait for them to finish
    wait $pid_1
    status_1=$?
    wait $pid_2
    status_2=$?
    wait $pid_3
    status_3=$?

    # Signal the recording server to finish recording this crawl
    send_end_to_recording_server
    sleep 1 # to make sure the writing has finished

    if [[ $status_1 -gt 0 || $status_2 -gt 0 || $status_3 -gt 0 ]]; then
        echo "Crawler exited, aborting remaining crawls."
        # Write name of failed crawl to file: seeder_domain,iteration,timestamp,statuses
        echo "$line,$i,$ds,$status_1,$status_2,$status_3" >> /data/list_of_failed_crawls.csv
        return 1
    fi
    return 0
}

mark_output_files_as_fails () {
    line=$1
    ds=$2
    attempt=$3
    # Crawler output files
    mv /data/crawlerOutput/safariProfile1/${line}_${ds}.txt /data/crawlerOutput/safariProfile1/failed_attempt${attempt}_${line}_${ds}.txt
    mv /data/crawlerOutput/safariProfile2/${line}_${ds}.txt /data/crawlerOutput/safariProfile2/failed_attempt${attempt}_${line}_${ds}.txt
    mv /data/crawlerOutput/chromeProfile/${line}_${ds}.txt /data/crawlerOutput/chromeProfile/failed_attempt${attempt}_${line}_${ds}.txt
}

run_three_crawlers_and_redo_failures () {
    line=$1
    ds=$2

    run_three_crawlers $line $ds
    three_crawlers_success=$?
    if [[ three_crawlers_success -gt 0 ]]; then
        # Mark failed output files, and try again once.
        # Files in test_results can get overwritten.
        echo "Running the three crawlers failed. Retrying once."
        mark_output_files_as_fails $line $ds 1
        run_three_crawlers $line $ds
        three_crawlers_success=$?
        if [[ three_crawlers_success -gt 0 ]]; then
            # Second attempt failed, move on.
            # But leave test_results files where they are, there still might be redirect chains in them depending on the error.
            echo "Running the three crawlers failed a second time. Moving on."
            mark_output_files_as_fails $line $ds 2
            return 1
        fi
    fi
    return 0
}

run_three_crawlers_from_input_file_and_redo_failures () {
    line=$1
    ds=$2
    i=$3
    run_three_crawlers_from_input_file $line $ds $i
    three_crawlers_success=$?
    if [[ three_crawlers_success -gt 0 ]]; then   
        echo "Running the three crawlers on iteration $i failed. Retrying once."
        # Mark the crawlerOutput files as fails
        # Files in test_results can get overwritten.
        mv /data/crawlerOutput/safariProfile1/${line}_${ds}_iter$i.txt /data/crawlerOutput/safariProfile1/failed_attempt1_${line}_${ds}_iter$i.txt
        mv /data/crawlerOutput/safariProfile2/${line}_${ds}_iter$i.txt /data/crawlerOutput/safariProfile2/failed_attempt1_${line}_${ds}_iter$i.txt
        mv /data/crawlerOutput/chromeProfile/${line}_${ds}_iter$i.txt /data/crawlerOutput/chromeProfile/failed_attempt1_${line}_${ds}_iter$i.txt

        # Retry once.
        run_three_crawlers_from_input_file $line $ds $i
        three_crawlers_success=$?
        if [[ three_crawlers_success -gt 0 ]]; then
            # Second attempt failed, move on.
            # But leave test_results files where they are, there still might be redirect chains in them depending on the error.
            echo "Running the three crawlers on iteration $i failed a second time. Moving on."

            # Mark the crawlerOutput files as fails.
            mv /data/crawlerOutput/safariProfile1/${line}_${ds}_iter$i.txt /data/crawlerOutput/safariProfile1/failed_attempt2_${line}_${ds}_iter$i.txt
            mv /data/crawlerOutput/safariProfile2/${line}_${ds}_iter$i.txt /data/crawlerOutput/safariProfile2/failed_attempt2_${line}_${ds}_iter$i.txt
            mv /data/crawlerOutput/chromeProfile/${line}_${ds}_iter$i.txt /data/crawlerOutput/chromeProfile/failed_attempt2_${line}_${ds}_iter$i.txt

            return 1
        fi
    fi
    return 0

}

send_start_to_recording_server () {
    line=$1
    ds=$2
    i=$3

    # Send the start commands
    output_file_sp1="/data/test_results/safariProfile1/extensionRequests/${ds}_${line}_iter${i}_extensionRequests.csv"
    output_file_sp2="/data/test_results/safariProfile2/extensionRequests/${ds}_${line}_iter${i}_extensionRequests.csv"
    output_file_chrome="/data/test_results/chromeProfile/extensionRequests/${ds}_${line}_iter${i}_extensionRequests.csv"

    curl --data "{\"START\":\"$output_file_sp1\",\"profile\":\"$profile_1\"}" http://127.0.0.1:8086
    curl --data "{\"START\":\"$output_file_sp2\",\"profile\":\"$profile_2\"}" http://127.0.0.1:8086
    curl --data "{\"START\":\"$output_file_chrome\",\"profile\":\"$chrome_profile\"}" http://127.0.0.1:8086
}

send_end_to_recording_server () {
    # Send the end commands to the recording server
    curl --data "{\"END\":\"\",\"profile\":\"$profile_1\"}" http://localhost:8086
    curl --data "{\"END\":\"\",\"profile\":\"$profile_2\"}" http://localhost:8086
    curl --data "{\"END\":\"\",\"profile\":\"$chrome_profile\"}" http://localhost:8086
}

send_start_redo_to_recording_server () {
    line=$1
    ds=$2
    i=$3

    output_file_sp1copy="/data/test_results/safariProfile1Copy/extensionRequests/${ds}_${line}_iter${i}_extensionRequests.csv"
    curl --data "{\"START\":\"$output_file_sp1copy\",\"profile\":\"safariProfile1Copy\"}" http://127.0.0.1:8086
    sleep 1
}

send_end_redo_to_recording_server () {
    curl --data "{\"END\":\"\",\"profile\":\"safariProfile1Copy\"}" http://localhost:8086
    sleep 1
}

export -f run_three_crawlers
export -f run_three_crawlers_from_input_file

while read -r line; do
    ds=`date '+%m-%d-%Y_%H:%M:%S_%p'`
    start_ts=`date +%s`
    echo "Starting crawl on seeder domain $line"

    # Delete the old profiles
    rm -r $profile_1
    rm -r $profile_2
    rm -r $chrome_profile

    # Create the new profiles
    cd /
    cp -r $base_profile_1 $profile_1
    cp -r $base_profile_2 $profile_2
    cp -r $base_chrome_profile $chrome_profile

    cd "/home/ec2-user/brave-redirection-recorder"

    # Start the controller
    node lib/controller & 
    controller_pid=$!

    # Start the recording server
    node extensions/recording_server > /data/recording_server_output/${ds}_${line}_recording_server.log &
    recorder_pid=$!

    # run_three_crawlers_and_redo_failures $line $ds
    run_three_crawlers $line $ds
    success=$?
    if [[ $success -gt 0 ]]; then 
        kill $controller_pid
        kill $recorder_pid
        continue
    fi

    # # Now run the fourth crawler, that re-uses safariProfile1
    echo "Starting redo crawler on seeder domain $line"
    send_start_redo_to_recording_server $line $ds 0
    timeout -k 150s 150s node rerun_crawler.js $line $ds 0 > /data/crawlerOutput/safariProfile1Copy/${line}_${ds}.txt
    send_end_redo_to_recording_server


    # Now run again, nine times, same profiles, to do the random walk from the seeder domain. 
    for i in {1..9}; do
        current_ts=`date +%s`
        if [[ $((start_ts + 600)) -le $current_ts ]]; then
            echo "Ending random walk, it has been 5 minutes"
            break
        fi
        echo "Starting random walk, iteration $i of seeder domain $line"
        run_three_crawlers_from_input_file_and_redo_failures $line $ds $i
        success=$?
        if [[ $success -gt 0 ]]; then 
            break
        fi

        # Now run the fourth crawler, that re-uses safariProfile1
        echo "Starting redo crawler on iteration $i of seeder domain $line"
        send_start_redo_to_recording_server $line $ds $i
        timeout -k 150s 150s node rerun_crawler.js $line $ds $i > /data/crawlerOutput/safariProfile1Copy/${line}_${ds}_iter$i.txt
        send_end_redo_to_recording_server
    done

    # Stop the controller and the recording server
    kill $controller_pid
    kill $recorder_pid

    # In case Chrome downloaded anything, clear the downloads folder to save disk space
    rm /home/ec2-user/Downloads/*
    # And clear out whatever junk Chrome has put in /tmp.
    rm -r /tmp/.com.google.Chrome.*
    # This command is useful to figure out what's using space. Replace / with the directory of interest.
    # sudo du -x -h / | sort -h | tail -40

done < /home/ec2-user/brave-redirection-recorder/tranco_top_1m_reversed.csv
